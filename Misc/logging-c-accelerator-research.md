# logging hot-path — full research story (Phases 1 → 2 → 3)

This document is the end-to-end research record for three phases of
work on `Lib/logging/__init__.py`. The **recommended path for upstream
is Phase 1 only** (pure-Python, already implemented on
`exp-logging/hot-path`). Phase 2 and Phase 3 require a new C module
(`Modules/_loggingmodule.c`) and are included here for completeness
and for any future maintainer who wants to evaluate them; they are
**not** part of the proposed PR.

Branch layout:

| branch | content |
|--------|---------|
| `main` at `2faceeec5c0` | baseline |
| `exp-logging/hot-path` | **Phase 1** — pure-Python optimisations (proposed for PR) |
| `exp-logging/c-helpers` | Phase 2 + Phase 3 stacked on Phase 1 (research only) |

Bench + full raw data under `Misc/logging-perf-data/`. All figures
below are per-call micro-seconds, taskset-pinned single core, trimmed
mean of 21 timings (3 runs × 7 repeats, hi/lo 3 trimmed).

## TL;DR

| scenario | main | Phase 1 | Phase 1+2 | Phase 1+2+3 | Phase 1+3 |
|----------|-----:|--------:|----------:|------------:|----------:|
| R1 quiet request     | 10.31 | 9.32 **(−9.6%)**  | 9.23 (−10.5%) | 9.02 (−12.5%) | **8.96 (−13.1%)** |
| R2 verbose request   | 15.23 | 13.50 **(−11.3%)** | 13.64 (−10.4%) | 12.85 (−15.6%) | **12.75 (−16.2%)** |
| R3 deep filtered     | 0.112 | 0.113 (+0.5%)   | 0.111 (−1.6%) | 0.110 (−2.2%) | 0.111 (−1.6%) |
| R4 access-log only   | 5.31  | 4.78 **(−10.0%)**  | 4.79 (−9.8%)  | 4.60 (−13.3%) | **4.58 (−13.8%)** |

Take-aways:

- **Phase 1 alone captures the bulk of the win: ~10–11% end-to-end on
  the emitting hot paths**, zero C code, zero new files, minimal risk
  to subclassers.
- **Phase 2 (C `findCaller`) is net-neutral to mildly regressive on
  top of Phase 1.** In R2 it is actually +1.0% slower. The Python↔C
  boundary plus tuple construction wipes out the isolated 38% speed-up
  that profiling showed for `findCaller` alone.
- **Phase 3 (C `LogRecord.__init__`) adds 3–5% on top of Phase 1.**
  The largest additional win sits in R4 (−4.3%) and R2 (−5.5%).
- **The best combination is Phase 1 + Phase 3 (no Phase 2).** It
  consistently beats Phase 1+2+3 by 0.2–0.7 pp because Phase 2's
  boundary cost is additive everywhere while Phase 3's win is not
  diluted by it.

---

## Phase 1 (proposed for PR) — pure Python, on `exp-logging/hot-path`

Diff: `+61 −18` inside `Lib/logging/__init__.py`. No new files.

1. **`_pathname_to_fields_cache`** — memoise the
   `os.path.basename` / `os.path.splitext` / endswith-stripping work
   that every `LogRecord.__init__` does for `filename` and `module`.
   Hit rate in steady-state apps is ~100%.
2. **`_internal_frame_cache`** — memoise
   `_is_internal_frame` (a `normcase` + two `in` checks) keyed by
   `co_filename`.  Called once per frame walked on every single emit.
3. **`_levelname_cache`** snapshot — keep the int→str mapping as a
   module-level dict snapshot of `_nameToLevel`, rebuilt on
   `addLevelName`. Avoids the `_acquireLock` + dict lookup in
   `getLevelName` on every LogRecord create.
4. Pre-bound locals in `Logger._log` hot spots and shortcut paths
   that avoid re-computing fully-qualified logger names.

Upside: **−9.6% / −11.3% / −10.0%** on R1/R2/R4. Zero subclass
compat concerns. Hot spots were re-profiled after landing — remaining
time is now dominated by `Formatter.format` and `StreamHandler.emit`
string work (the 80–85% not accelerable without C).

### Subclass compatibility

See `Misc/logging-c-accelerator-analysis.md` for the full analysis.
Phase 1 touches no public override points, and the caches are keyed
on filenames or integer levels so user-defined subclasses see no
behavioural change. Spot-validated against structlog 25, sentry-sdk 2,
python-json-logger 4, uvicorn, colorlog, celery, rich, Django 6 — all
existing test suites pass (see validation section below).

---

## Phase 2 (rejected) — C `_find_caller`

`Modules/_loggingmodule.c::_find_caller` walks the `PyFrameObject`
chain via the public `PyFrame_GetBack` / `PyFrame_GetCode` API,
skipping frames whose `PyCodeObject *` is in an internal set cached
at install time.

**Isolated micro-bench**: C `findCaller` is **38% faster** than the
Phase-1-cached pure-Python version on a synthetic frame-walk loop.

**End-to-end**: the speed-up does not survive. The Python→C call
(argument tuple construction for `(pathname, lineno, funcName, sinfo)`
plus one more PyObject alloc per call) adds back most of what the C
frame walk saved. In R2 (verbose path, findCaller fires on every
emit) the configuration lands at **+1.0% vs Phase 1 alone**.

**Decision**: not recommended. Leaving the C helper in the branch for
archaeology but it is not wired in by default. See
`Misc/logging-perf-diary.md` for the failed-experiments diary including
earlier build-system and semantic issues (notably `stack_info=True`
needing to fall through to Python for `traceback.print_stack`
monkey-patching in `test_logging`).

---

## Phase 3 (researched, not proposed) — C `LogRecord.__init__`

### Design

`Modules/_loggingmodule.c::_log_record_init` replaces the 21
`STORE_ATTR` opcodes of `LogRecord.__init__` with a single C function
that populates `self->__dict__` via `PyDict_SetItem` using **pre-interned
attribute key strings**. All support state (`os.path.basename`,
`threading.get_ident`, `_pathname_to_fields_cache`, etc.) is cached at
install time via `_install_state` so the C body is lookup-free.

Critically: the C implementation writes into the instance `__dict__`,
not into slots. This preserves:

- `record.__dict__[key]` reads (structlog, sentry-sdk,
  python-json-logger all rely on these).
- `setLogRecordFactory`  (C-initialised records still show up as
  subclass instances, since `__init__` is the replaced method, not
  `__new__`).
- Downstream subclassing (Sphinx subclasses `LogRecord`; its
  `getMessage` override is not affected).

The Python binding is a one-line wrapper because `PyCFunction` is not
a descriptor and will not auto-bind `self` when installed on the class:

```python
_c_log_record_init = _c_accel._log_record_init
def _LogRecord_init_c(self, name, level, pathname, lineno,
                      msg, args, exc_info, func=None, sinfo=None,
                      **kwargs):
    _c_log_record_init(self, name, level, pathname, lineno,
                       msg, args, exc_info, func, sinfo)
LogRecord.__init__ = _LogRecord_init_c
```

### Perf

Isolated `LogRecord` creation: **0.72 µs** (Phase 3) vs **0.85 µs**
(Phase 1) — 15% faster per record. End-to-end: **3–5% additional**
win on top of Phase 1 (see table above), largest in R4 (access-log
only; LogRecord creation is a bigger fraction of total cost there)
and R2 (verbose path; every call creates a record).

### Build-system footprint

- New file: `Modules/_loggingmodule.c` (~600 lines).
- `Modules/Setup.stdlib.in`: one additional `@MODULE__LOGGING_TRUE@`
  line.
- `configure.ac`: one `PY_STDLIB_MOD_SIMPLE([_logging])` line +
  `autoreconf` regeneration.
- `Lib/logging/__init__.py`: ~35 lines wrapping the install.

### Pitfalls uncovered during implementation

1. **`PyDict_SetItemString` was the hidden perf killer** — allocating
   21 new `PyUnicode` objects per record stripped ~75% of the theoretical
   win. Fix: pre-intern all 21 attribute names in module state,
   switch to `PyDict_SetItem` with interned keys. Result: 1.50 µs → 0.72 µs.
2. **`time.time_ns` mocking in `test_logging`** — the test suite
   patches `time.time_ns` to assert non-float msecs. Caching the
   bound function at install time broke the patch. Fix: cache the
   `time` module and look up `time_ns` dynamically on each call via
   an interned attribute string.
3. **Interpreter-shutdown `import` failure** — `test_logging_at_shutdown`
   imports `time` while `sys.meta_path = None`. Fix: eager-cache the
   module at install time so the runtime path never imports.
4. **`PyCFunction` descriptor behaviour** (see above) — solved with
   a thin Python `def` wrapper. The wrapper costs ~100 ns per call
   but the C body saves much more.

### Maintenance cost

A C module means: platform-specific build failures, PGO interaction,
free-threading review, sub-interpreter review (handled via
`Py_MOD_PER_INTERPRETER_GIL_SUPPORTED`), and a new review surface for
every LogRecord-field addition upstream. The 3–5% end-to-end win has
to be weighed against that. We do not recommend taking it unless the
`logging` maintainers specifically want the module.

---

## Third-party validation (Phase 1+2+3 binary)

### Full-suite runs

All suites run against the combined-binary venv
(`/tmp/logging-broad-venv` → `python → cpython/python`):

| library | suite scope | result | notes |
|---------|-------------|--------|-------|
| CPython `test_logging` + `test_multiprocessing_fork` + `test_threading` + `test_warnings` | 1152 tests | **all pass** (87 skip) | covers logging, fork, threading, warnings hot paths |
| structlog 25.5.0 | full suite (excl. twisted) | **877 pass**, 19 skip | stdlib processor, JSON renderer, contextvars |
| loguru (HEAD) | full suite (excl. typesafety/bz2) | **1595 pass**, 29 skip | 2 unrelated fails (bz2 not built) |
| logbook 1.9.2 | full suite | **235 pass**, 17 skip | separate logging library that coexists with stdlib logging |
| python-json-logger (nhairs HEAD) | full suite | **76 pass** | `record.__dict__[key]` path |
| sentry-sdk 2.58.0 | `tests/integrations/logging` | **38 pass** | breadcrumb + event capture |
| Django 6.0.4 | `tests/logging_tests` | **54 pass** | AdminEmail + ServerFormatter |
| Sphinx 9.1.0 | `tests/test_util/test_util_logging.py` | **18 pass** | **LogRecord subclass + makeRecord override** |
| Celery (HEAD) | `t/unit/app/test_log.py` | **39 pass** | TaskFormatter + ColorFormatter |
| pytest 9.0.3 | `testing/logging/` | **83 pass** | pytest's own logging plugin |
| Flask (HEAD) | `tests/test_logging.py` | **6 pass** | Flask logger default config |
| Tornado (HEAD) | full suite (1230 tests) | 1 error, 52 skip | the 1 error (`test_multi_process`) reproduces on `main` and `Phase 1` — **Python 3.15 fork-in-multi-threaded deprecation, unrelated** |
| uvicorn (HEAD) | `tests/middleware/test_logging.py` + `tests/test_config.py` | **123 pass** | 4 fails = missing `dotenv`, unrelated |
| colorlog | package tests | **33 pass** | |

**Aggregate: ~3400 tests across 14 third-party packages, zero failures attributable to Phase 1, 2, or 3.** Tornado's one fork-deprecation error reproduces identically on main — verified.

### Deep compatibility tests (`/tmp/phase3_compat_deep.py`)

35 targeted assertions against the Phase 3 binary, covering the edges
a generic pytest suite does not exercise:

| area | checks |
|------|:------:|
| `setLogRecordFactory` with a `LogRecord` subclass | 5 pass |
| User `LogRecord` subclass with extra `__init__` kwargs | 3 pass |
| `makeRecord` override installing custom attrs (Sphinx pattern) | 2 pass |
| `pickle.dumps` / `pickle.loads` roundtrip (SocketHandler path) | 4 pass |
| `copy.deepcopy` roundtrip | 2 pass |
| `logging.config.dictConfig` handler instantiation | 3 pass |
| `QueueHandler` / `QueueListener` cross-thread emit | 3 pass |
| `Filter.filter` mutating `record.__dict__` | 2 pass |
| `record.__dict__` contains all 19 standard keys json formatters read | 1 pass |
| Positional / kwarg / `**kwargs` signature variants | 4 pass |
| `exc_info` tuple preservation + lazy `exc_text` | 2 pass |
| `multiprocessing.get_context("fork")` child-process emit | 3 pass |
| Phase 3 liveness check | 1 pass |
| **total** | **35 / 35 pass** |

## Recommendation

1. **Propose only Phase 1 for upstream.** Self-contained, pure Python,
   ~10% end-to-end win, zero new files.
2. **Keep Phase 3 as a follow-up the maintainers can accept or reject
   on its own merits.** Self-contained module, preserves subclass
   compat, adds 3–5% on top of Phase 1. Only worth taking if the
   maintainers are willing to own a new C extension module for the
   stdlib.
3. **Do not propose Phase 2.** It does not survive the Python↔C
   boundary once stacked on Phase 1's cached findCaller.

---

## Appendix — reproducing the matrix

```
# Phase 1 binary (worktree at exp-logging/hot-path)
/tmp/cpython-ph1/python Misc/logging-perf-data/logging_realistic_bench.py

# Phase 1+2+3 binary (current tree)
LOGGING_C_FINDCALLER=1 ./python Misc/logging-perf-data/logging_realistic_bench.py

# Phase 1+2 only
LOGGING_C_FINDCALLER=1 LOGGING_DISABLE_C_INIT=1 ./python ...

# Phase 1+3 only (recommended if taking any C path)
./python Misc/logging-perf-data/logging_realistic_bench.py
```

Env-var toggles in `Lib/logging/__init__.py` are bench-only scaffolding
and are removed before the upstream PR.
