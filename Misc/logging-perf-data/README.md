# Logging Perf Raw Data

Raw artifacts backing `Misc/logging-perf-diary.md`.

## Bench scripts

- `logging_realistic_bench.py` — four scenarios modeled on FastAPI /
  Starlette production patterns:
    - R1 quiet request (INFO root; mixed filtered + emitted)
    - R2 verbose request (DEBUG root; all emit)
    - R3 deep filtered (8-level logger name; all filtered)
    - R4 access-log only (uvicorn.access-shape)
  Handlers write to a `BytesIO` sink via `TextIOWrapper`, so we measure
  CPU not I/O.

- `logging_hotpath_profile.py` — `cProfile`-based hot-path breakdown
  used to identify `_is_internal_frame` and `LogRecord.__init__` as
  the biggest targets.

- `starlette_logging_bench.py` — end-to-end-ish benchmark using
  Starlette's `TestClient` against a `Route` that emits 4 log calls
  per request. Requires `starlette` + `httpx` installed in the venv
  pointing at the CPython build under test. Use e.g.

      uv venv --python=/path/to/python /tmp/venv
      VIRTUAL_ENV=/tmp/venv uv pip install starlette httpx
      taskset -c 0 /tmp/venv/bin/python starlette_logging_bench.py

## JSON files

| File | Branch state |
| --- | --- |
| `logging-baseline.json` | Clean `main` (2faceeec), no logging changes |
| `logging-opt12.json` | After `_is_internal_frame` cache + `pathname` cache |
| `logging-opt123.json` | + main-thread ident/name cache |
| `logging-opt1234.json` | + `PercentStyle.usesTime` cache (current tip) |

Each record contains per-scenario: `n` (iteration count), `runs` (raw
7-sample timings), `min`, `median`, `trimmed_mean`. Primary statistic
is `trimmed_mean` (7 samples, trim 1 hi / 1 lo).

## Compare two runs

    ./python -c "
    import json
    def load(p): return json.load(open(p))
    a = load('logging-baseline.json')
    b = load('logging-opt1234.json')
    for k in sorted(a):
        am = a[k]['trimmed_mean']; bm = b[k]['trimmed_mean']
        print(f'{k:25s}  {am:.4f} -> {bm:.4f}  ({(bm-am)/am*100:+.1f}%)')"
