# A `_logging` C accelerator — subclass-compatibility analysis

Question: is it worth adding a C accelerator for `Lib/logging/__init__.py`
in the style of `Modules/_pickle.c`?

This document maps **which parts of the public `logging` API are
actually subclassed / overridden in the real-world Python ecosystem**,
measured statically across 3,723 `.py` files from 40+ heavily-used
packages. The answer informs a concrete per-method classification:
safe to C-accelerate, must stay Python, or conditional.

## Methodology

Two AST passes in `Misc/logging-perf-data/logging_subclass_analysis.py`:

1. **Pass 1** — walk `Lib/logging/__init__.py` to enumerate all 17
   classes and their methods, flagging methods whose docstring calls
   them out as extension points ("override", "factory method",
   "subclass", etc.).

2. **Pass 2** — walk every `.py` file in a venv containing:
   `structlog, python-json-logger, sentry-sdk, colorlog, loguru, rich,
   celery, boto3, botocore, fastapi, starlette, uvicorn, django,
   sphinx, dill, cloudpickle, joblib, httpx, flask, tornado, aiohttp,
   pytest, _pytest, werkzeug` (and their transitive deps). For each
   class definition, build a local import map to determine whether a
   base class like `Formatter` refers to `logging.Formatter` or to an
   unrelated same-named class (pygments, for instance, has its own
   `Formatter`). For each real `class X(logging.Y):` definition, record
   which of `Y`'s methods the subclass overrides.

Scale: **3,723 files scanned, 34 import-verified subclasses of logging
classes** across 15+ packages.

## 2026-04-18 prototype result

A later prototype branch (`exp-logging/c-helpers`) validated the
subclassing story here but exposed four behavioral hazards that are not
visible from subclass counts alone:

- caching `pathname` by arbitrary key breaks unhashable
  `os.PathLike` inputs unless the cache is limited to `str` / `bytes`
- caching the main-thread name at import time regresses later renames;
  only the ident should be memoized, with `.name` read live
- caching `usesTime()` once at formatter construction breaks code that
  rebinds `_style._fmt` later
- `_startTime` must be read with `PyLong_AsLongLong`, not
  `PyLong_AsSsize_t`, or 32-bit builds overflow at import time

After fixing those, the rebuilt branch still beat stock 3.15 on the
realistic logging and Starlette request benches, but its advantage over
the Python-only `exp-logging/hot-path` branch was small and noisy. The
long-term lesson is that subclass compatibility is not the blocker;
behavioral parity around `record.__dict__` semantics is.

## Override heat map (third-party only)

Where `★` = docstring-flagged extension point. `Δ` = count of
third-party packages that override the method. The `packages` column
names the packages that actually do the override.

### Classes with many subclasses

| Base | # subclasses | Packages |
| --- | ---: | --- |
| `Formatter` | **11** | django, python-json-logger, colorlog, dill, structlog, uvicorn, tornado, _pytest, sphinx, celery |
| `Filter` | **12** | sphinx, django, tornado, sentry_sdk |
| `Handler` | 4 | rich, sentry_sdk, celery, django |
| `StreamHandler` | 1 | werkzeug |
| `FileHandler` | 1 | _pytest |
| `NullHandler` | 1 | _pytest |
| `Logger` | 1 | structlog (via `setLoggerClass`) |
| `LogRecord` | 1 | sphinx |
| `LoggerAdapter` | 1 | dill |
| `Manager` | 0 | — |
| `PercentStyle` | 1 | _pytest |
| `StrFormatStyle` / `StringTemplateStyle` / `BufferingFormatter` / `Filterer` / `PlaceHolder` | 0 | — |

### `Formatter` (most-overridden base)

| method | line | ★ | Δ | packages |
| --- | ---: | :-: | ---: | --- |
| `__init__` | 598 |  | **8** | celery, colorlog, dill, django, python-json-logger, structlog, tornado, uvicorn |
| `format` | 699 |  | **8** | celery, dill, django, python-json-logger, sphinx, structlog, tornado |
| `formatException` | 658 |  | 2 | celery, python-json-logger |
| `formatMessage` | 683 |  | 2 | colorlog, uvicorn |
| `formatStack` | 686 | ★ | 1 | python-json-logger |
| `formatTime` | 631 |  | 1 | _pytest |
| `usesTime` | 677 |  | 0 | — |
| `__repr__` | 625 |  | 0 | — |

**Verdict**: `Formatter.__init__`, `Formatter.format`, `formatException`,
`formatMessage`, `formatStack`, `formatTime` are all override targets in
the wild. A C `Formatter` class would break structured-logging libraries
(python-json-logger, structlog) and uvicorn's access formatter. **Keep
`Formatter` entirely in Python.**

### `Filter`

| method | line | ★ | Δ | packages |
| --- | ---: | :-: | ---: | --- |
| `__init__` | 789 |  | 7 | django, sphinx, tornado |
| `filter` | 803 |  | **12** | django, sentry_sdk, sphinx, tornado |
| `__repr__` | 800 |  | 0 | — |

**Verdict**: `filter()` is overridden ubiquitously. The whole point of
the `Filter` class is to be subclassed. **Keep in Python.**

### `Handler`

| method | line | ★ | Δ | packages |
| --- | ---: | :-: | ---: | --- |
| `__init__` | 934 |  | 2 | django, rich |
| `emit` | 1004 | ★ | 2 | django, rich |
| `close` | 1048 | ★ | 0 | — |
| `flush` | 1039 | ★ | 0 | — |
| `handleError` | 1063 |  | 1 | celery |
| `handle`, `format`, `acquire`, `release`, `setFormatter`, `setLevel`, `createLock`, `_at_fork_reinit`, `get_name`, `set_name` | — |  | 0 | — |

**Verdict**: `emit` is THE handler extension point — every custom
handler overrides it. `__init__` is frequently chained via `super()`.
`close` / `flush` are documented extension points. But the rest
(acquire, release, handle, format, setFormatter, setLevel, etc.) are
**never overridden in the sample**. A C `Handler` that preserves virtual
dispatch through `self.emit()` / `self.close()` / `self.flush()` —
the way pickle's C code calls back into Python for
`__reduce__` / `persistent_id` — **would work correctly** for the
override-able methods while letting the inherited infrastructure
(thread locks, level-gated dispatch, `handle(record)` scaffolding)
run at C speed.

### `LogRecord`

| method | line | ★ | Δ | packages |
| --- | ---: | :-: | ---: | --- |
| `__init__` | 295 |  | **0** | — |
| `getMessage` | 388 |  | 1 | sphinx |
| `__repr__` | 384 |  | 0 | — |

**Crucially**: `LogRecord.__init__` has **zero** direct subclass
overrides across the entire scanned ecosystem. The only two
`LogRecord`-relevant extension points in practice are:

- `Logger.makeRecord` (documented factory method, 0 overrides seen in
  my sample but the docstring invites it).
- `logging.setLogRecordFactory()` — a public function that installs a
  custom LogRecord factory. **structlog uses this** to install
  `_FixedFindCallerLogger` (well, actually via `setLoggerClass`, not
  `setLogRecordFactory`). My scan found zero uses of
  `setLogRecordFactory` in 3,723 files.

**Verdict**: `LogRecord.__init__` is a strong candidate for C
acceleration. But there's one hard constraint that affects any
acceleration strategy (C or Python): `record.__dict__[key]` lookups
must still work. structlog explicitly does this at
`structlog/stdlib.py:906` and `processors.py:917` to copy attributes
into a dict. A C-type LogRecord using `__slots__` would break
`record.__dict__[key]`; a C-type using a per-instance `__dict__` is
workable but gives up some of the C speed-up benefit.

### `Logger`

| method | line | ★ | Δ | packages |
| --- | ---: | :-: | ---: | --- |
| `findCaller` | 1595 |  | 1 | structlog |
| `makeRecord` | 1629 | ★ | 0 | — |
| `__init__`, `_log`, `addHandler`, `callHandlers`, `critical`, `debug`, `error`, `exception`, `fatal`, `getChild`, `getChildren`, `getEffectiveLevel`, `handle`, `hasHandlers`, `info`, `isEnabledFor`, `log`, `removeHandler`, `setLevel`, `warn`, `warning` | — |  | 0 | — |

**Verdict**: `findCaller` is overridden once (structlog); `makeRecord`
is a documented extension point. The public `debug` / `info` / `warning`
/ `error` / `critical` / `exception` / `log` methods are **never**
overridden in the wild. `_log`, `callHandlers`, `handle`, `addHandler`,
`removeHandler`, `getEffectiveLevel`, `isEnabledFor` etc. are also
untouched.

So: **a C `Logger` class preserving virtual dispatch for `findCaller`
and `makeRecord` would be broadly compatible.** The 25 other methods
are safe to run as C directly.

### Methods actually read from LogRecord (third-party)

Sorted by occurrence count across the 3,723-file sample:

    26  record.msg            << cheap anyway
    25  record.exc_info       << cheap anyway
    20  record.args           << cheap anyway
    16  record.levelno        << cheap anyway
    13  record.levelname      << cheap (dict lookup)
    11  record.getMessage     << method call, calls msg % args
    10  record.name
     9  record.exc_text
     6  record.stack_info
     6  record.pathname
     5  record.created
     3  record.lineno
     3  record.asctime        << set by Formatter, not __init__
     2  record.threadName     << sentry_sdk
     2  record.thread         << sentry_sdk
     2  record.processName    << sentry_sdk
     2  record.process
     2  record.funcName
     1  record.msecs

**Finding**: the expensive-to-populate fields
(`thread`/`threadName`/`processName`/`process`/`taskName`) are read by
only 2–3 places, primarily `sentry_sdk.integrations.logging`. But
those readers DO need the fields populated correctly; we can't simply
skip them. Any optimization that defers their computation must make
the deferred value available through both `record.foo` and
`record.__dict__['foo']`.

## Per-method C-acceleration classification

Legend:
- **SAFE_TO_ACCELERATE** — 0 overrides seen; no documented override-
  invitation; no extension-point semantics. A C implementation of this
  method is safe as long as it calls virtual-dispatch methods (`self.X()`)
  through the type slot protocol (respects MRO).
- **LIKELY_SAFE** — 1–2 overrides seen in the sample; no documented
  override-invitation. Safe to C-accelerate **but the C code must call
  back to Python via `self.method(...)` for any overridable peer
  methods**.
- **EXTENSION_POINT** — documented override-invitation in docstring or
  widely overridden (3+ packages). The C side must always dispatch
  through the type slot; never inline or bypass.
- **WIDELY_OVERRIDDEN** — overridden by 3+ packages. Same constraint
  as EXTENSION_POINT.
- **DUNDER_SKIP** — `__repr__` / `__reduce__` variants; they don't
  matter for perf and can stay Python.

### SAFE_TO_ACCELERATE (86 methods)

These are the C accelerator's working set. Every method here is
effectively internal-to-the-module plumbing that users don't customize.

Full list in the raw report
(`Misc/logging-perf-data/logging-subclass-broad.txt`). Notable entries:

- `Logger.{debug, info, warning, error, critical, exception, log,
   isEnabledFor, getEffectiveLevel, addHandler, removeHandler,
   callHandlers, handle, _log}` — the hottest call chain. Nothing
   overrides these.
- `Logger.makeRecord` — documented as extension-point but 0
   overrides observed; should remain virtual-dispatchable anyway
   (belongs in LIKELY_SAFE).
- `Handler.{handle, format, acquire, release, setLevel, setFormatter,
   set_name, get_name, createLock, _at_fork_reinit}` — the
   infrastructure that wraps each handler's `emit()`.
- `Manager.*` — all 8 methods; user code does not subclass Manager.
- `PercentStyle.{_format, format, validate, usesTime}` and
  equivalents for `StrFormatStyle`, `StringTemplateStyle` — Style
  classes are not overridden in the sample (except `_pytest` hacks
  `PercentStyle`, but not the format path).
- `LogRecord.{__init__}` — the init is not subclassed directly, but the
  class itself is subclassed once (sphinx) — see LIKELY_SAFE below.

### LIKELY_SAFE (11 methods)

Override count 1–2. Safe to C-accelerate if virtual-dispatchable.

- `Formatter.{formatException, formatMessage, formatTime}` — 1-2
  overrides each (pytest, colorlog, uvicorn, celery). A C
  implementation must call these via the type slot so overrides win.
- `Handler.{__init__, handleError}` — 1-2 overrides (django, rich,
  celery). `__init__` override is most commonly a `super().__init__()`
  then attribute stores; a C `__init__` that dispatches
  `super().__init__()` correctly is fine.
- `LogRecord.getMessage` — 1 override (sphinx).
- `Logger.findCaller` — 1 override (structlog). Minor; structlog's
  custom logger replaces the whole Logger class via
  `setLoggerClass(_FixedFindCallerLogger)`.
- `LoggerAdapter.__init__` — 1 override (dill).
- `PercentStyle.{__init__, format}` — 1 override each (pytest).
- `StreamHandler.__init__` — 1 override (werkzeug).

### WIDELY_OVERRIDDEN (4 methods — must stay overridable)

| method | Δ | packages |
| --- | ---: | --- |
| `Formatter.__init__` | 8 | celery, colorlog, dill, django, python-json-logger, structlog, tornado, uvicorn |
| `Formatter.format` | 8 | celery, dill, django, python-json-logger, sphinx, structlog, tornado |
| `Filter.__init__` | 7 | django, sphinx, tornado |
| `Filter.filter` | 12 | django, sentry_sdk, sphinx, tornado |

These are where the extensibility contract is. Whatever we C-accelerate
must never call inlined versions of these; always dispatch through the
type.

### EXTENSION_POINT (6 methods — docstring-flagged)

| method | Δ | packages |
| --- | ---: | --- |
| `Formatter.formatStack` | 1 | python-json-logger |
| `Handler.close` | 0 | — (but documented) |
| `Handler.emit` | 2 | django, rich |
| `Handler.flush` | 0 | — (but documented) |
| `Logger.makeRecord` | 0 | — (but documented) |
| `LoggerAdapter.process` | 1 | dill |

All must dispatch through the type slot.

## Design proposal: narrow `_logging` accelerator

Based on the data above, the sweet spot is **not a full rewrite** but a
targeted accelerator for the hot call path, preserving virtual
dispatch for every override-able method. Concretely:

### Shape 1 (minimal, recommended first step): C-accelerate `LogRecord`

- Implement `_logging.LogRecord` as a C type with a regular instance
  `__dict__` (not `__slots__`). Preserves `record.__dict__[key]`
  compatibility with structlog / PercentStyle._format.
- `tp_init` does everything `LogRecord.__init__` does, at C speed.
  Probably 3-5× faster than the Python version. Saves ~3-4 µs per
  emit.
- `getMessage` stays a Python method so sphinx's override wins via MRO.
- `setLogRecordFactory()` still works — it swaps the callable used by
  `Logger.makeRecord`. A user factory returning a Python subclass
  of `_logging.LogRecord` works unchanged; users returning a
  completely unrelated class also work (logging already handles
  this).
- Risk: the one observed `LogRecord` subclass (sphinx) works fine
  because it inherits from the C base.

Estimated win on top of our current pure-Python patches: 15–30% on
the emitted path. Engineering cost: ~300 lines of C + bindings.
Ongoing maintenance: whenever Lib/logging/__init__.py's `LogRecord.__init__`
gains a field, the C version has to gain it too.

### Shape 2 (larger, better ROI if approved): `_logging.Logger`

- C type `_logging.Logger`. Ships a C `_log()`, `handle()`,
  `callHandlers()`, `isEnabledFor()`, `getEffectiveLevel()`, `debug()`,
  `info()`, `warning()`, `error()`, `critical()`, `exception()`,
  `log()` plus `addHandler()` / `removeHandler()` infra.
- Calls `self.makeRecord(...)` via type slot — so Python subclass
  overrides win.
- Calls `self.findCaller(...)` via type slot (structlog override wins).
- Calls `self.handle(...)` via type slot.
- Calls `self.filter(record)` via type slot for Filter dispatch.
- Calls handler's `emit`, `handle`, `handleError` via type slots.

This is where the per-call framework overhead (attribute loads,
dict lookups, Python bytecode dispatch) gets replaced by C.

Estimated win: another 20-40% on the emitted path. Engineering cost:
~1,000 lines of C. Maintenance: every Logger behavior change has to
land in two places.

### Shape 3 (probably not worth it): `_logging.Handler` / `_logging.Formatter`

- Both are extension-point-heavy. Handler has `emit`/`close`/`flush`
  as the intended override points; Formatter has `format`/`__init__`.
- C versions would have to dispatch every public method through the
  type slot. The remaining C-only work is the thread-lock acquire/
  release, level check, and the `self.filter(record)` invocation — all
  of which are already cheap.
- Likely 5-10% gain, at high maintenance cost. Not recommended.

### Shape 4 (leave alone entirely)

- `Filter` — subclassed everywhere, the only meaningful method is
  `filter()` which IS the override point. Zero benefit from C.
- `LoggerAdapter`, `BufferingFormatter`, `PlaceHolder`, `Manager`
  instance internals — not hot enough.

## Recommendation

**Ship the pure-Python optimizations first** (the `exp-logging/hot-path`
branch). They're a 10-12% win with zero compat risk.

**If the core team wants more**, pursue **Shape 1** (C `LogRecord`)
first. It's the narrowest useful scope:
- 0 direct subclass overrides in the 3,723-file sample.
- 1 `setLoggerClass` user (structlog); 0 `setLogRecordFactory` users.
- Preserves `record.__dict__[key]` by keeping a regular instance dict.
- Saves measurable per-emit time on the hottest method in the module.

**Shape 2** (C `Logger`) is the natural follow-up if Shape 1 proves
itself — larger scope, but the override heat map says `Logger.*`
methods are almost never touched.

**Shapes 3 and 4 should stay Python indefinitely.** The override data
is clear: `Formatter.format`, `Formatter.__init__`, `Filter.filter`,
`Handler.emit` are THE extensibility points of the module. Touching
them breaks real-world structured-logging libraries.

## Limitations of this analysis

- **Sample size**: 3,723 files across 40+ packages. Large PyPI
  ecosystem analysis (e.g. via sourcegraph search) would catch cases
  my set misses. Likely discovery: more `Filter.filter` overrides; few
  new `LogRecord.__init__` overrides.
- **AST-only**: doesn't catch dynamic subclass creation
  (`type(name, bases, dict)`). Libraries that build custom loggers
  metaprogrammatically (rare but exists) would be missed.
- **No runtime monkey-patching**: some libraries monkey-patch
  `logging.LogRecord` (I didn't look). A PyPI-scale grep for
  `logging.LogRecord =` and `logging.LogRecord.__init__ =` would close
  that gap.
- **Doesn't catch `super().__init__()` calls from non-logging
  base-class subclasses that still depend on LogRecord's shape** —
  the structlog `__dict__[key]` usage is an example of downstream
  dependence.

## Supporting artifacts

- `Misc/logging-perf-data/logging_subclass_analysis.py` — the full AST
  analyzer used above, including the import-map resolution that
  filters out false positives (pygments's `Formatter`, joblib's
  `Logger`, etc.).
- `Misc/logging-perf-data/logging-subclass-broad.txt` — the full raw
  report from scanning the 40-package venv.

## Provenance

Generated 2026-04-18 as a follow-up to the `exp-logging/hot-path`
pure-Python branch, in response to the question: "is a C API version
of logging worthwhile, like the pickle setup?"
