# Heapq / Asyncio Comparator Experiment

Reusable artifacts for the `exp-heapq/asyncio-tuple-compare` branch.

This directory records the usage scan, benchmark corpus, and smoke
checks used to investigate whether `_heapq` should specialize the
comparison path for the tuple / namedtuple shapes that show up in
`sched`, `kombu`, `celery`, and adjacent code.

Artifacts:

- `heapq_asyncio_usage_scan.py`
  - scans `Lib`, `Lib/test`, and representative third-party packages
    under `/tmp/perf-extra-pkgs` for `heapq` / `call_at` / `call_later`
    usage
- `heapq_asyncio_bench.py`
  - mixed micro + real-workload benchmark corpus
- `heapq_asyncio_checks.py`
  - smoke checks for the benchmark corpus and loopback server harnesses
- generated JSON artifacts
  - `usage-scan.json`
  - `baseline.json`
  - `c*.json` candidate benchmark outputs

Outcome summary:

- The original tuple-specialization hypothesis for `asyncio` was only
  half-right. Current `asyncio` still stores `TimerHandle` objects, not
  `(when, seq, handle)` tuples, so service-facing event-loop workloads
  do not move much from `_heapq` tuple fast paths alone.
- The real tuple / namedtuple story is elsewhere: `sched`,
  `kombu.asynchronous.timer`, and `celery.beat` all use tuple-like heap
  items with a `float` timestamp and integer priority / sequence
  prefixes.
- The best candidate was a small `_heapq` helper that recognizes
  tuple-like objects using the built-in tuple rich-compare slot and
  short-circuits the first three fields:
  `float` timestamp, `int` priority, then `int` sequence.
- That candidate produced large wins on tuple-heavy micros and moderate
  wins on `sched` / `kombu`, while staying effectively flat on the real
  `uvicorn` / `fastapi` loopback workloads.

See `Misc/heapq-asyncio-perf-diary.md` for the full narrative,
candidate-by-candidate results, and recommendation.
