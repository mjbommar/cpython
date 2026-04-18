# logging hot-path — experiment diary

Branch: `exp-logging/hot-path`, off `main` at `2faceeec5c0`. No dependency
on the marshal or pickle branches.

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

## Validation

- `test_logging`: 282/282 pass.
- `test_asyncio`: 2708/2708 pass.
- `test_unittest`: 1096/1096 pass.
- `test_warnings`: 191/191 pass.
- `test_http_cookies`: 33/33 pass.
- Full CPython suite (`./python -m test -j24 --timeout=600 -w`):
  **468 test files, 48,928 tests, 0 failures.**

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

`_main_thread_ident` / `_main_thread_name` are read once at import
from `threading.main_thread()`. They're never mutated. If someone
renames the main thread at runtime, `threadName` in log records would
still reflect the import-time name — but renaming the main thread is
vanishingly rare and the existing docs don't commit to reflecting it.

## What we didn't try

- **C-level accelerator for `LogRecord`.** The `_logging` module
  exists (for `Logger.info/debug/etc` fast paths) but does not
  implement `LogRecord`. Porting LogRecord to C would be invasive
  and was out of scope.
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

1. This branch ships as a self-contained PR — ~75 lines of change,
   all in `Lib/logging/__init__.py`, measurable 3% win on real
   Starlette request handling.
2. A follow-up exploring per-Formatter field-demand propagation
   would unlock the next tier of savings (skip `threadName`,
   `processName`, `taskName` computation when no formatter reads
   them). Higher complexity; worth a separate issue.
3. A C accelerator for `LogRecord` would be the ceiling — probably
   2-5× gain for this module — but that's a multi-week project and
   belongs on its own roadmap.

## Provenance

Generated 2026-04-18 during a stdlib perf-opportunity exploration
following the marshal + pickle rounds. Raw JSON and bench scripts in
`Misc/logging-perf-data/`.
