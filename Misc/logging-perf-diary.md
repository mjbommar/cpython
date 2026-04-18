# logging C helpers — experiment diary

Branch: `exp-logging/c-helpers`, derived from `exp-logging/hot-path`,
off `main` at `2faceeec5c0`. This file started as the hot-path diary;
the original profiling and Python-only benchmark notes still matter, but
the branch-specific status for the `_logging` C-helper port lives here.

## 2026-04-18 post-review update

The first `_logging` port kept the hot-path wins but regressed four
observable behaviors. `fix/logging-review-chelpers` fixes all four:

- `_pathname_to_fields_cache` now only caches `str` / `bytes`
  pathnames, so unhashable `os.PathLike` inputs fall back to the
  pre-existing split logic instead of raising `TypeError`.
- The main-thread fast path now caches the main-thread object plus its
  ident and reads `_main_thread.name` live, so runtime renames are
  reflected again.
- `PercentStyle.usesTime()` and `StringTemplateStyle.usesTime()` now
  self-invalidate when `_style._fmt` is rebound, so formatters that
  start without `%(asctime)s` and later add it still populate
  `record.asctime`.
- `_startTime` in `_loggingmodule.c` now uses `PyLong_AsLongLong`,
  which avoids import-time overflow on 32-bit builds.

### Validation added with the fix set

- `Lib/test/test_logging.py` now covers the unhashable path-like case,
  main-thread rename visibility, and `_style._fmt` rebinding.
- The rebuilt branch passes those three tests under `./python -m
  unittest`.
- A direct repro against the rebuilt original branch still shows the
  pre-fix failures (`TypeError`, stale `MainThread`, and missing
  `asctime`).

## Original hypothesis (from the stdlib perf-ideas brainstorm)

Three things were flagged in `Misc/cpython-perf-ideas.md` under the
top-ranked "Logging hot path" target:

- `LogRecord.__init__` eagerly populates many fields (thread, processName,
  taskName, module, filename) that the configured formatter often
  doesn't read.
- `Logger.callHandlers` walks the parent chain per emit.
- `Logger.getEffectiveLevel` walks the parent chain per emit.

The plan was three sub-experiments:

- L1: lazy `LogRecord` fields
- L2: `Logger.getEffectiveLevel` cache
- L3: `Logger.callHandlers` handler-chain cache

All landed or were ruled out. The shape of what shipped differs from
the original plan; below records why.

## Findings that changed the plan

**L2 is already in place.** `Logger.isEnabledFor` (at
`Lib/logging/__init__.py:1768`) already has a per-level cache
(`self._cache[level]`), invalidated via `Manager._clear_cache()` on
every `setLevel`. The "uncached walk" the graph-theorist lens flagged
is only the first call per (logger, level). No room.

**L1 in the originally-proposed form is unsafe.**
`PercentStyle._format` uses `self._fmt % record.__dict__` — a `%`
operator on a dict, which uses `dict.__getitem__` and raises `KeyError`
on missing keys. Python `__getattr__`-based laziness doesn't help
here: `record.__getattr__('threadName')` is never called because the
formatter looks up `record.__dict__['threadName']` directly.

Making `record.__dict__` itself a subclass that falls back to a
computation function is possible but invasive — it means every
`record.__dict__` access (including user-written formatters reading
the raw record) potentially triggers computation, with knock-on
effects on pickling, reprs, and existing code that iterates
`record.__dict__` expecting plain-dict semantics.

**The real opportunity is cheaper:** *cache the pure-function results
that `LogRecord.__init__` and `findCaller` compute on every emit*.
None of them depend on record state; all of them are deterministic
from their inputs (`pathname`, `co_filename`, the main-thread ident,
the format string).

**L3 is a small win behind a lot of complexity.** The handler-chain
walk in `callHandlers` takes ~200 ns per emit (profile: 13 ms of 525 ms
total). Caching it with correct invalidation across `addHandler` /
`removeHandler` / `setLevel` / `propagate` would require Manager
epoch bookkeeping. Not worth the surface area.

## Profile (main baseline)

### Emitted-path microbench (Scenario B in `logging_hotpath_profile.py`)

30,000 emissions of `logger.info("request=%s status=%d took=%.3fms",
"req-42", 200, 0.123)` through a `StreamHandler` to a BytesIO sink
with format `%(asctime)s %(levelname)s %(name)s:%(lineno)d - %(message)s`.

    531 ms total
    - Logger._log          504 ms cumtime  (every emit goes through here)
    - Logger.handle        250 ms cumtime
      - callHandlers       232 ms cumtime  (parent chain walk)
      - Handler.handle     219 ms cumtime
        - emit             188 ms cumtime  (format + write)
    - Logger.makeRecord    168 ms cumtime
      - LogRecord.__init__ 157 ms cumtime
    - Logger.findCaller     70 ms cumtime
      - _is_internal_frame  37 ms cumtime  (90_000 calls — 3x per emit)

Per emit: ~17.5 µs.

### Disabled-path microbench (Scenario A)

300,000 calls to `logger.debug(...)` that get filtered by root `INFO`:

    86 ms total
    - Logger.debug       50 ms cumtime
    - Logger.isEnabledFor 14 ms cumtime

Per call: ~287 ns. Already tight; the `_cache[level]` fast path is
working as designed.

## Realistic benchmarks

Two benches bundled in `Misc/logging-perf-data/`:

- `logging_realistic_bench.py` — four scenarios modeled on FastAPI /
  Starlette production shapes (R1 quiet, R2 verbose, R3 deep
  filtered, R4 uvicorn.access-style). Per-scenario trimmed-mean
  timings across 7 repeats.
- `starlette_logging_bench.py` — Starlette `TestClient` driving an
  actual `Route` with 4 `logger.debug/info(...)` calls per request,
  handlers writing to an in-memory BytesIO sink.

## Experiment ledger

| # | Idea | Status | Δ on R1 (quiet req) |
| --- | --- | --- | ---: |
| L1a | `_is_internal_frame` result cache on `co_filename` | **shipped** | −? (part of combined) |
| L1b | `(pathname) → (filename, module)` cache | **shipped** | −? |
| L1c | main-thread ident/name cache | **shipped** | small, see below |
| L1d | `PercentStyle.usesTime()` cache (format string is immutable-ish) | **shipped** | 1–2% additional |
| L2  | `Logger.getEffectiveLevel` cache | already present as `isEnabledFor._cache` | n/a |
| L3  | Handler chain cache in `callHandlers` | **deferred** — ~200 ns/emit, complex invalidation | n/a |
| L1-lazy | lazy `LogRecord` attributes via `__getattr__` | **rejected** — breaks `record.__dict__[key]` format lookup | n/a |

### Cumulative deltas on the realistic bench (vs clean `main`)

| Scenario | base | opt1+2 | opt1+2+3 | opt1+2+3+4 (shipped) |
| --- | ---: | ---: | ---: | ---: |
| `R1_quiet_request`   | 10.12 µs/iter | 9.16 (−9.5%) | 9.15 (−9.5%) | **9.02 (−10.9%)** |
| `R2_verbose_request` | 14.96         | 13.40 (−10.4%) | 13.42 (−10.3%) | **13.14 (−12.2%)** |
| `R3_deep_filtered`   |  0.11         |  0.11 (flat) |  0.11 (flat) | **0.11 (flat)** |
| `R4_access_log_only` |  5.27         |  4.75 (−9.9%) |  4.66 (−11.6%) | **4.62 (−12.4%)** |

### Starlette end-to-end benchmark

In-process `TestClient` against a `Starlette` app routing to a handler
that emits 2 DEBUGs + 2 INFOs per request. Handlers attached to
`StreamHandler(BytesIO)` so measurement is CPU, not I/O.

| Config | `main` | F4 branch | Δ per request |
| --- | ---: | ---: | ---: |
| INFO  (quiet)   | 331.7 µs | 321.8 µs | **−10.0 µs (−3.0%)** |
| DEBUG (verbose) | 330.2 µs | 322.0 µs | **−8.2 µs (−2.5%)** |

The microbench number (−12%) is larger than the end-to-end number
(−3%) because the request handler includes route dispatch, JSON
response serialization, and `TestClient` transport overhead that our
optimization doesn't touch. **−3% on the full request wall-time of a
Starlette app is the headline for users**; the microbench is how we
verified the fix landed on the right code.

### Post-review delta vs the original `c-helpers` prototype

After rebuilding both the original branch and the fixed branch with the
same system `openssl` / `zlib` headers, the safety fixes were close to
flat on the realistic bench:

| Scenario | original `c-helpers` | fixed branch | Δ |
| --- | ---: | ---: | ---: |
| `R1_quiet_request`   | 9.709 µs | 9.777 µs | +0.7% |
| `R2_verbose_request` | 13.566   | 13.662   | +0.7% |
| `R3_deep_filtered`   | 0.122    | 0.119    | −2.6% |
| `R4_access_log_only` | 4.937    | 4.878    | −1.2% |

`starlette_logging_bench.py` was noisier, so the honest summary is the
mean of three rebuilt-binary passes rather than a single run:

| Config | original `c-helpers` | fixed branch | Δ |
| --- | ---: | ---: | ---: |
| INFO  (quiet)   | 293.0 µs | 301.0 µs | +2.7% |
| DEBUG (verbose) | 299.4 µs | 300.0 µs | +0.2% |

The fix set therefore costs little on the realistic bench and is
roughly flat on the end-to-end Starlette bench.

### Position vs stock interpreters after the fixes

Using the rebuilt fixed branch, stock system `python3` 3.14.4, and a
stock 3.15 build from `main` at `cecf564073f`, with two confirmatory
passes averaged:

| Scenario | stock 3.14.4 | stock 3.15 `main` | fixed `c-helpers` | vs 3.14 | vs 3.15 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `R1_quiet_request`   | 10.023 µs | 11.659 µs | 10.299 µs | +2.8% | **−11.7%** |
| `R2_verbose_request` | 15.090    | 17.337    | 14.538    | **−3.6%** | **−16.1%** |
| `R3_deep_filtered`   | 0.102     | 0.125     | 0.128     | +25.0% | +2.0% |
| `R4_access_log_only` | 5.266     | 6.001     | 5.216     | **−1.0%** | **−13.1%** |

For the end-to-end Starlette bench, averaged across two passes:

| Config | stock 3.14.4 | stock 3.15 `main` | fixed `c-helpers` | vs 3.14 | vs 3.15 |
| --- | ---: | ---: | ---: | ---: | ---: |
| INFO  (quiet)   | 311.2 µs | 318.5 µs | 297.9 µs | **−4.3%** | **−6.5%** |
| DEBUG (verbose) | 297.3    | 331.1    | 291.2    | **−2.0%** | **−12.0%** |

Net: after the review fixes, this branch is still clearly ahead of
stock 3.15 on every emitted-path workload that matters here, and still
modestly ahead of stock 3.14 on `R2`, `R4`, and the Starlette request
bench. `R1` and `R3` are not wins over 3.14.

## 2026-04-18 deeper follow-up

The original diary closed with the fixed-vs-stock interpreter story.
This follow-up widened the evidence base in two ways:

- package-backed validation on a 3.15-native environment
- one additional `_loggingmodule.c` cleanup idea, measured and rejected

### Broader package ecosystem coverage

Imports succeeded on both `main` and the rebuilt branch for:

- `starlette`
- `fastapi`
- `httpx`
- `dataclasses_json`
- `jsonschema`
- `flask`
- `django`
- `structlog`
- `uvicorn`
- `gunicorn`
- `celery`
- `simplejson`
- `orjson`
- `ujson`

Not all of those packages exercise stdlib logging directly, but they
were the full 3.15 package set used for compatibility checks while the
logging-specific workloads focused on the wrappers and formatters that
actually hit `logging` hot paths.

`Misc/logging-perf-data/third_party_logging_bench.py` was added to make
the package-backed reruns reproducible.

### Package-backed logging bench (vs rebuilt `main`)

All results below are trimmed-mean microseconds per emitted record:

| scenario | `main` | `c-helpers` | delta |
| --- | ---: | ---: | ---: |
| `structlog_stdlib` | 8.84 µs | 7.80 µs | **−11.8%** |
| `uvicorn_access`   | 9.33    | 8.55    | **−8.4%** |
| `flask_app_logger` | 5.37    | 4.67    | **−13.0%** |
| `django_server`    | 7.16    | 6.28    | **−12.3%** |
| `celery_color`     | 5.34    | 4.60    | **−13.9%** |

The deterministic smoke outputs for the package-backed formatter paths
matched `main` byte-for-byte for the `structlog`, `uvicorn`, `flask`,
`django`, and `celery` cases.

### Additional idea tested and rejected

I tried one more `_loggingmodule.c` cleanup after the review-fix branch
was stable:

- replace a few dynamic attr lookup + `CallNoArgs` pairs with direct
  `PyObject_CallMethodNoArgs(...)` plus interned method names for
  `time.time_ns`, `multiprocessing.current_process`,
  `asyncio.current_task`, and `Task.get_name`

`test_logging` still passed, but the results did not justify keeping
it:

| scenario | branch baseline | extra patch | delta |
| --- | ---: | ---: | ---: |
| `R1_quiet_request` | 9.92 µs | 9.96 µs | +0.4% |
| `R2_verbose_request` | 13.91 | 14.05 | +1.0% |
| `R4_access_log_only` | 4.97 | 5.04 | +1.4% |
| `structlog_stdlib` | 7.48 | 7.49 | +0.1% |
| `uvicorn_access` | 8.06 | 8.13 | +0.9% |
| `celery_color` | 4.42 | 4.25 | −3.8% |

That patch was reverted. The remaining branch recommendation is
unchanged: the C-helper path is real and broadly compatible, but the
Python-only `exp-logging/hot-path` branch is still the better first PR
because it gets most of the win with far less maintenance surface.

## Validation

Historical validation from the Python-only hot-path branch:

- `test_logging`: 282/282 pass.
- `test_asyncio`: 2708/2708 pass.
- `test_unittest`: 1096/1096 pass.
- `test_warnings`: 191/191 pass.
- `test_http_cookies`: 33/33 pass.
- Full CPython suite (`./python -m test -j24 --timeout=600 -w`):
  **468 test files, 48,928 tests, 0 failures.**

Branch-specific reruns for `exp-logging/c-helpers` on 2026-04-18:

- rebuilt interpreters import `ssl`, `zlib`, and `_logging`
- `./python -m unittest -v
  test.test_logging.FormatterTest.test_uses_time_after_style_rebind
  test.test_logging.LogRecordTest.test_pathlike_pathname_unhashable
  test.test_logging.LogRecordTest.test_main_thread_rename_reflected`:
  **3/3 pass**
- compiled-binary `logging_realistic_bench.py` and
  `starlette_logging_bench.py` rerun against the rebuilt interpreters

## Safety argument for the two persistent caches

`_internal_frame_cache` and `_pathname_to_fields_cache` are
module-level dicts that grow monotonically as the process encounters
new source files. Bounds:

- Worst case size = total number of distinct `co_filename` values ever
  seen by `_is_internal_frame` / `LogRecord.__init__`. For a
  Python process, this is bounded by the number of source files of
  all imported modules — typically O(hundreds) to O(low thousands).
- Entries are stable: both caches hold results of pure functions
  (`os.path.normcase`, `os.path.basename`, `os.path.splitext`) of
  immutable string keys. No invalidation event is possible unless
  something mutates `os.path.basename` at runtime, which would
  break far more than just logging.
- Memory: each entry is ~200 bytes for the cache value + string key
  reference. 1000 entries ≈ 200 KB — comparable to `sys.modules`.

`_main_thread_ident` / `_main_thread` are read once at import from
`threading.main_thread()`. The import-time lookup only memoizes the
identity; `threadName` now comes from `_main_thread.name` at record
creation time, so later main-thread renames are reflected.

## What we didn't try

- **Deeper C acceleration beyond the current helper port.** This branch
  moves `LogRecord` hot-path work into `_logging`, but it still leaves
  most of `logging` in Python. A full C `Logger` / `Handler`
  accelerator remains a separate project.
- **Per-Formatter field-demand propagation** (parse `%(fieldname)s`
  from `_fmt`, tell Logger not to populate unread fields). The cleanest
  path to safely skipping work, but requires coordination between
  Formatter (which knows its format string) and Logger (which builds
  records without knowing about handlers yet). Significant API surface.
- **Pre-computing `findCaller`'s frame skip count for stacklevel=1**.
  Currently walks with `_is_internal_frame`; the cache helps. A
  hardcoded "skip 3 frames" would be faster but fragile to refactors
  of `_log`.

## Recommended next moves

1. Keep `exp-logging/hot-path` as the low-risk PR candidate. Its
   Python-only subset landed most of the win and had the cleanest
   review story.
2. If `exp-logging/c-helpers` moves forward, keep the three new
   regression tests and the 32-bit `_startTime` fix as non-negotiable.
   The extra C complexity is only justified if the branch keeps a clear
   advantage over stock builds.
3. The next substantive optimization target is still per-Formatter
   field-demand propagation. Handler-chain caching remains too small a
   win for its invalidation complexity.

## Provenance

Generated 2026-04-18 during a stdlib perf-opportunity exploration
following the marshal + pickle rounds. Raw JSON and bench scripts in
`Misc/logging-perf-data/`.
