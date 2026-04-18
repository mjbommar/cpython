# Asyncio Event-Loop Experiment

Reusable artifacts for the `exp-asyncio/eventloop-hotpaths` branch.

This directory records the benchmark, usage-scan, and smoke-check
infrastructure used to explore `asyncio` / `selectors` / `_heapq`
event-loop hot paths under both microbenchmarks and real loopback ASGI
workloads.

Artifacts:

- `asyncio_eventloop_usage_scan.py`
  - scans stdlib and representative third-party packages for
    `asyncio`-hot API usage such as `call_soon`, `call_later`,
    `create_task`, `add_reader`, and `create_server`
- `asyncio_eventloop_bench.py`
  - mixed micro + real-workload benchmark corpus
- `asyncio_eventloop_checks.py`
  - smoke checks for the benchmark corpus and server harnesses
- generated JSON artifacts
  - `usage-scan.json`
  - `baseline.json`
  - `c*.json` candidate benchmark outputs

Outcome summary:

- The branch ended as a documented weak/negative-result experiment,
  not a filing candidate.
- The best simple patch was an `EpollSelector.select` exact-event fast
  path, but it only produced small wins on selector / echo-heavy paths
  and stayed roughly flat on the real `uvicorn` loopback workloads.
- `TimerHandle.__lt__` and tiny `call_at` / `Handle` tweaks did move
  the timer micros, but the service-facing gains were too small to
  justify another standalone PR.
- `_run_once` local-binding rewrites did not help and were dropped.

See `Misc/asyncio-eventloop-perf-diary.md` for the full narrative and
recommendation.

Typical usage:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/asyncio-eventloop-perf-data/asyncio_eventloop_checks.py

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/asyncio-eventloop-perf-data/asyncio_eventloop_usage_scan.py \
  > Misc/asyncio-eventloop-perf-data/usage-scan.json

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/asyncio-eventloop-perf-data/asyncio_eventloop_bench.py \
  --label baseline --output Misc/asyncio-eventloop-perf-data/baseline.json
```
