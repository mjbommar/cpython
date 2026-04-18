# Heapq / Asyncio Comparator Experiment Diary

Branch: `exp-heapq/asyncio-tuple-compare`

Date: 2026-04-18

## Goal

Follow up on the service-workload profiling pass around `_heapq` and
check whether a small comparator specialization is worth pursuing.

The original perf-ideas note assumed that `asyncio`'s `_scheduled` heap
still stored `(when, seq, handle)` tuples. Current `main` does **not**:
it stores `TimerHandle` objects. So the branch had two jobs:

- re-check the actual item shapes being pushed through `_heapq`
- test whether tuple / namedtuple specialization still buys enough on
  the real non-asyncio users (`sched`, `kombu`, `celery`, etc.) to
  justify a small C patch

## Usage inventory

`Misc/heapq-asyncio-perf-data/heapq_asyncio_usage_scan.py` scanned
`Lib`, `Lib/test`, and representative third-party packages under
`/tmp/perf-extra-pkgs`.

High-level counts from `usage-scan.json`:

- roots:
  - `Lib`: `24`
  - `Lib/test`: `45`
  - `site-packages`: `31`
- pattern totals:
  - `call_later`: `45`
  - `call_at`: `12`
  - `heapq.heappush`: `7`
  - `heapq.heappop`: `7`
  - `heapq.heapify`: `7`
  - `heapq.heapreplace`: `3`
  - `heapq.heappushpop`: `1`
  - `PriorityQueue`: `1`
- top packages / modules:
  - `test_asyncio`: `35`
  - `asyncio`: `15`
  - `celery`: `11`
  - `dateutil`: `7`
  - `uvicorn`: `4`
  - `sched.py`: `3`
  - `kombu`: `3`
  - `queue.py`: `4`

The scan also corrected the original hypothesis:

- `asyncio.base_events` pushes a `TimerHandle` object
- `sched`, `kombu`, and `celery.beat` push tuple / namedtuple shapes
- `dateutil.rrule` uses custom objects with `__lt__`

Representative shapes from direct code inspection:

- `sched.Event(time, priority, sequence, action, args, kwargs)`
- `kombu.scheduled(eta, priority, entry)`
- `celery.event_t(time, priority, entry)`
- `asyncio.TimerHandle`

## Benchmark corpus

The branch-local harness is
`Misc/heapq-asyncio-perf-data/heapq_asyncio_bench.py`.

Workloads:

- micros
  - `M1_timerhandle_pushpop`
  - `M2_namedtuple3_pushpop`
  - `M3_sched_event_pushpop`
  - `M4_namedtuple3_heapify_pop`
  - `M5_due_timer_run_once`
- wrappers / real-ish paths
  - `R1_sched_run`
  - `R2_dateutil_rruleset`
  - `R3_kombu_timer`
  - `R4_asyncio_echo`
  - `R5_uvicorn_plain`
  - `R6_uvicorn_fastapi`

The ASGI paths reuse the earlier loopback `uvicorn` harness from the
`exp-asyncio/eventloop-hotpaths` branch.

## Profiling snapshot

Two baseline profiles drove the candidate list:

### tuple-heavy micro mix

`40x M1 + 40x M2 + 40x M3`

Dominant time:

- `_heapq.heappop`
- `asyncio.events.TimerHandle.__lt__`
- `_heapq.heappush`
- namedtuple constructors in the synthetic tuple workloads

Interpretation:

- the plain `_heapq` compare path is genuinely hot for tuple-like heaps
- `asyncio` itself is still dominated by `TimerHandle.__lt__`, so a
  tuple-only `_heapq` patch is not expected to move service workloads
  much

### wrapper mix

`60x R1_sched_run + 60x R3_kombu_timer`

Dominant time:

- `_heapq.heappop`
- `Lib/sched.py:run`
- `kombu.asynchronous.timer.Entry.__lt__`
- `_heapq.heappush`

Interpretation:

- `sched` and `kombu` are real consumers of tuple-like `_heapq`
  traffic
- the wrapper-level workloads are heavy enough to validate a small C
  helper

## Candidate patterns

I tested eight concrete shapes:

1. `C1`: exact `tuple[len=3]`, first-slot exact-float fast path in
   `siftdown` only
2. `C2`: the same exact-float fast path in `siftup` only
3. `C3`: exact `tuple[len=3]`, first-slot exact-float fast path in both
   `siftdown` and `siftup`
4. `C4`: tuple-like (`PyTuple_Check` + built-in tuple rich-compare
   slot), `len=3`, first-slot exact-float fast path
5. `C5`: tuple-like `len in {3, 6}`, first-slot exact-float plus
   second-slot exact-int fast path
6. `C6`: `C5` plus third-slot exact-int fast path
7. `C7`: `C6` helper routed through the remaining `_heapq` compare
   sites (`heappushpop`, max-heap helpers)
8. `C8`: `C6` plus the previously explored Python-side
   `TimerHandle.__lt__` exact-type fast path

All raw outputs are stored under
`Misc/heapq-asyncio-perf-data/c*.json`.

## Results

Baseline (5 samples) is in `baseline.json`.

### `C1` exact `tuple[3]` first-float in `siftdown`

Too small and too mixed:

- `M2_namedtuple3_pushpop`: `-3.0%`
- `R4_asyncio_echo`: `-1.1%`
- `R2_dateutil_rruleset`: `+1.6%`
- `R3_kombu_timer`: `+0.1%`

Conclusion:

- insufficient

### `C2` exact `tuple[3]` first-float in `siftup`

Worse overall:

- `M2_namedtuple3_pushpop`: `-3.6%`
- `R3_kombu_timer`: `+3.5%`
- `R4_asyncio_echo`: `+8.2%`

Conclusion:

- reject

### `C3` exact `tuple[3]` first-float in both paths

Still not convincing:

- `M2_namedtuple3_pushpop`: `-2.9%`
- `M3_sched_event_pushpop`: `-2.5%`
- `R1_sched_run`: `+2.2%`
- `R4_asyncio_echo`: `+4.1%`

Conclusion:

- exact-tuple-only is the wrong scope

### `C4` tuple-like `len=3`, first-float prefix

This is where the branch got interesting:

- `M2_namedtuple3_pushpop`: `-14.0%`
- `M4_namedtuple3_heapify_pop`: `-11.9%`
- `R3_kombu_timer`: `-5.4%`
- `R1_sched_run`: `+9.9%`

Conclusion:

- namedtuple support is essential
- but `sched.Event` still regresses, because its shape is longer and the
  helper is still too shallow

### `C5` tuple-like `len in {3, 6}`, float + int prefix

This turned into the first strong all-around candidate:

- `M2_namedtuple3_pushpop`: `-16.4%`
- `M3_sched_event_pushpop`: `-13.0%`
- `M4_namedtuple3_heapify_pop`: `-11.3%`
- `R1_sched_run`: `-5.5%`
- `R2_dateutil_rruleset`: `-1.5%`
- `R3_kombu_timer`: `-6.1%`
- `R4_asyncio_echo`: effectively flat (`-0.1%`)
- `R5_uvicorn_plain`: effectively flat (`-0.1%`)
- `R6_uvicorn_fastapi`: `-0.3%`

Conclusion:

- real candidate

### `C6` tuple-like `len in {3, 6}`, float + int + int prefix

This was the best pure `_heapq` result.

Exploratory run (5 samples):

- `M2_namedtuple3_pushpop`: `-24.3%`
- `M3_sched_event_pushpop`: `-20.6%`
- `M4_namedtuple3_heapify_pop`: `-22.2%`
- `R1_sched_run`: `-13.2%`
- `R2_dateutil_rruleset`: `-1.4%`
- `R3_kombu_timer`: `-4.9%`
- `R4_asyncio_echo`: `+0.6%`
- `R5_uvicorn_plain`: `-0.0%`
- `R6_uvicorn_fastapi`: `+0.0%`

Confirmatory rerun (7 samples) stayed strong on the important tuple
paths:

- `M2_namedtuple3_pushpop`: `-21.0%`
- `M3_sched_event_pushpop`: `-14.0%`
- `M4_namedtuple3_heapify_pop`: `-23.7%`
- `R1_sched_run`: `-10.3%`
- `R4_asyncio_echo`: essentially flat (`+0.1%`)
- `R5_uvicorn_plain`: `-0.1%`
- `R6_uvicorn_fastapi`: `-0.1%`

The smaller wrapper workloads (`dateutil` and `kombu`) were noisy in the
mixed bench, so I also ran a longer focused main-vs-branch comparison
(`30x` per sample, `7` samples) against a rebuilt `main` binary:

- `real_sched_run`: `-13.3%`
- `real_dateutil_rruleset`: `-0.9%`
- `real_kombu_timer`: `-0.8%`

Conclusion:

- this is the best branch-local result

### `C7` route all remaining `_heapq` compare sites through the helper

This overreached:

- `M2_namedtuple3_pushpop`: `-25.0%`
- `M3_sched_event_pushpop`: `-17.9%`
- `R1_sched_run`: `-13.6%`
- `R4_asyncio_echo`: `+6.2%`
- `R3_kombu_timer`: only `-0.7%`

Conclusion:

- do not widen the helper indiscriminately

### `C8` `C6` plus Python-side `TimerHandle.__lt__` exact-type path

This mostly confirmed that the heapq result and the `TimerHandle`
result are separable:

- tuple-heavy numbers stayed close to `C6`
- `R4_asyncio_echo` returned to flat
- the aggregate win over plain `C6` was not large enough to justify
  mixing a Python-side `asyncio` change into the `_heapq` branch

Conclusion:

- keep the branch focused on `_heapq`

## Validation

Final branch state keeps the `C6` `_heapq` helper only.

Stdlib validation passed:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python -m test -j4 \
  test_heapq test_sched test_queue test_asyncio \
  test_free_threading.test_heapq
```

Result:

- `36` test files OK
- `3` skipped (`Windows`-only files plus free-threading heapq under a
  GIL-enabled build)

Branch-local smoke checks passed:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/heapq-asyncio-perf-data/heapq_asyncio_checks.py
```

Third-party validation:

- import smoke passed for:
  `dateutil.rrule`, `kombu.asynchronous.timer`, `celery.beat`,
  `jsonschema`, `uvicorn`, `starlette`, `fastapi`, `httpx`, `anyio`,
  `asgiref`, `gunicorn.asgi.protocol`
- available third-party test suite:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python -m pytest -q \
  /tmp/perf-extra-pkgs/jsonschema/tests \
  --ignore=/tmp/perf-extra-pkgs/jsonschema/tests/test_jsonschema_test_suite.py
```

Result:

- `484` passed
- the ignored file depends on an external checkout of the
  JSON-Schema-Test-Suite and is not runnable in this environment

Remaining theorized semantic risk:

- if the first compared slot is an exact `float` `NaN`, the current C
  helper can diverge from normal tuple comparison semantics
- why: the helper checks direct `<` / `>` on slot `0`, and if both are
  false it continues on to slots `1` and `2`; ordinary tuple comparison
  would stop at slot `0` once the floats compare unequal
- this was not observed in the tested corpora, but it should be treated
  as a real edge case until the helper is adjusted or a regression test
  is added

## Final assessment

This branch is a **real but narrow** C optimization candidate.

Important conclusions:

- the original asyncio tuple hypothesis was stale; `_heapq` tuple
  specialization does **not** materially accelerate the current
  `asyncio` service workloads because those heaps still store
  `TimerHandle` objects
- tuple / namedtuple specialization **does** help real consumers of
  `_heapq`: `sched`, `kombu`, and Celery-like timer structures
- the winning helper is not “generic tuple compare in C”; it is a small
  prefix specialization for the common
  `(float, int, int, ...)` ordering shape while preserving the normal
  rich-compare fallback
- the remaining blocker to calling it PR-ready is the `NaN` edge case
  in the first float slot

## Recommendation

Keep the branch on the `C6` helper:

- tuple-like object
- built-in tuple rich-compare slot
- length `3` or `6`
- direct compare of:
  - slot `0` exact `float`
  - slot `1` exact `int`
  - slot `2` exact `int`
- fall back to `PyObject_RichCompareBool(..., Py_LT)` otherwise

I would treat this as a plausible medium-priority `_heapq` PR if we
want a small C optimization with good stdlib coverage. I would **not**
promote it ahead of the already stronger logging / AST / ABC work, and
I would not frame it as an asyncio optimization anymore. Before filing,
the `NaN` first-slot behavior should be fixed or explicitly guarded by
tests.

## Artifacts

Branch-local artifacts live in `Misc/heapq-asyncio-perf-data/`:

- `heapq_asyncio_usage_scan.py`
- `heapq_asyncio_bench.py`
- `heapq_asyncio_checks.py`
- `usage-scan.json`
- `baseline.json`
- candidate outputs:
  - `c1_tuple3_exact_firstfloat_siftdown.json`
  - `c2_tuple3_exact_firstfloat_siftup.json`
  - `c3_tuple3_exact_firstfloat_both.json`
  - `c4_tuplelike3_firstfloat_both.json`
  - `c5_tuplelike36_firstfloat_secondint.json`
  - `c6_tuplelike36_firstfloat_secondint_thirdint.json`
  - `c6_tuplelike36_firstfloat_secondint_thirdint_confirm.json`
  - `c7_all_heapq_cmp_sites_tuple_prefix.json`
  - `c8_c6_plus_timerhandle_exact_type.json`
