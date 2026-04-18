# Asyncio Event-Loop Hot-Path Experiment Diary

Branch: `exp-asyncio/eventloop-hotpaths`

Date: 2026-04-18

## Goal

Follow up on the service-workload profiling pass with a real
`asyncio`/ASGI benchmark corpus and test whether the hottest event-loop
paths have a small, safe optimization:

- `Lib/asyncio/base_events.py:_run_once`
- `Lib/asyncio/selector_events.py:_process_events`
- `Lib/selectors.py:EpollSelector.select`
- `Lib/asyncio/events.py:TimerHandle` comparisons / construction

The focus was deliberately narrow: no `ceval` work, no framework-local
rewrites, and no speculative C extension shape unless a pure-Python
result justified going deeper.

## Usage inventory

`Misc/asyncio-eventloop-perf-data/asyncio_eventloop_usage_scan.py`
scanned `Lib/asyncio`, `Lib/test`, and representative third-party
packages under `/tmp/perf-extra-pkgs`.

High-level counts from `usage-scan.json`:

- roots:
  - `Lib/asyncio`: `172`
  - `Lib/test`: `1349`
  - `site-packages`: `361`
- pattern totals:
  - `add_reader`: `55`
  - `add_writer`: `38`
  - `asyncio` imports: `182`
  - `asyncio.sleep`: `514`
  - `call_at`: `26`
  - `call_later`: `63`
  - `call_soon`: `254`
  - `create_server`: `89`
  - `create_task`: `426`
  - `get_running_loop`: `195`
  - `start_server`: `40`
- top third-party packages in the scan:
  - `prompt_toolkit`: `93`
  - `anyio`: `64`
  - `gunicorn`: `49`
  - `uvicorn`: `49`
  - `celery`: `37`
  - `asgiref`: `25`
  - `kombu`: `20`
  - `django`: `9`

This was enough to justify the branch: the service-profile signal was
not just FastAPI noise.

## Benchmark corpus

The branch-local benchmark harness is
`Misc/asyncio-eventloop-perf-data/asyncio_eventloop_bench.py`.

Workloads:

- micros
  - `M1_call_later_heap`
  - `M2_due_timer_run_once`
  - `M3_cancelled_timer_cleanup`
  - `M4_process_events`
- real-ish paths
  - `R1_selector_socketpair`
  - `R2_asyncio_echo`
  - `R3_uvicorn_plain`
  - `R4_uvicorn_fastapi`

The real ASGI paths use `uvicorn` with `loop="asyncio"` over loopback
TCP, not `TestClient`.

## Profiling snapshot

Two baseline `cProfile` snapshots mattered:

### `real_uvicorn_plain(iterations=8, warmup=2)`

Dominant time:

- `_socket.socket.recv`
- `select.epoll.poll`
- `asyncio.base_events._run_once`
- `selectors.EpollSelector.select`

Interpretation:

- the plain loopback ASGI path is mostly socket + selector wait cost
- `_run_once` is visible, but not dominant enough that local Python
  attribute-hoisting alone is likely to move much

### timer-heavy micro mix

`40x micro_call_later_heap + 40x micro_due_timer_run_once`

Dominant time:

- `asyncio.events.TimerHandle.__lt__`
- `asyncio.base_events.call_at`
- `asyncio.events.TimerHandle.__init__`
- `_heapq.heappush`
- `_heapq.heappop`
- millions of `isinstance(...)` calls inside `TimerHandle.__lt__`

Interpretation:

- the timer path has a real pure-Python comparison / construction hotspot
- it is worth testing tiny `TimerHandle` and `call_at`-side changes

## Candidate patterns

I tested nine concrete shapes:

1. `C1`: `TimerHandle.__lt__` exact-type fast path
2. `C2`: full `TimerHandle` comparison-family exact-type fast path
3. `C3`: direct `loop._debug` access in `Handle.__init__` / `cancel()`
4. `C4`: guard `call_at` / `call_soon` traceback cleanup with `self._debug`
5. `C5`: `_run_once` local-binding / hot-path rewrite
6. `C6`: `_process_events` exact-mask fast path + locals
7. `C7`: `EpollSelector.select` exact-event-mask fast path + locals
8. `C8`: combined Python hot paths (`C1 + C3 + C4 + C7`)
9. `C9`: combined Python hot paths without `TimerHandle.__lt__`

All candidate raw outputs are stored under
`Misc/asyncio-eventloop-perf-data/c*.json`.

## Results

Baseline (7 samples) is in `baseline.json`.

### `C1` `TimerHandle.__lt__` exact-type fast path

Exploratory run (5 samples) looked good on the timer path:

- `M2_due_timer_run_once`: about `-8.1%`
- `M3_cancelled_timer_cleanup`: about `-20.0%`
- `R2_asyncio_echo`: about `-3.4%`

But confirmatory rerun (7 samples) was much weaker:

- `M2_due_timer_run_once`: `-13.8%`
- `M3_cancelled_timer_cleanup`: `-9.2%`
- `R2_asyncio_echo`: `-1.9%`
- `R3_uvicorn_plain`: `+0.2%`
- `R4_uvicorn_fastapi`: essentially flat (`-0.0%`)

Conclusion:

- real timer-path win exists
- service impact is too small and noisy to justify a standalone PR

### `C2` full comparison-family fast path

This was the wrong extension:

- `M1_call_later_heap`: `+19.0%`
- `M2_due_timer_run_once`: `+13.4%`

Even though the service workloads did not collapse, the core timer
micros regressed enough that the broader comparison-family patch should
be rejected.

### `C3` direct `_debug` attribute

Small timer improvements:

- `M2_due_timer_run_once`: `-8.5%`
- `M3_cancelled_timer_cleanup`: `-21.9%`

Real workloads were basically noise:

- `R2_asyncio_echo`: `-1.2%`
- `R3_uvicorn_plain`: `-0.0%`
- `R4_uvicorn_fastapi`: `-0.4%`

Conclusion:

- safe, but too small

### `C4` `call_at` / `call_soon` debug-guard cleanup

Mostly noise, but modestly favorable:

- `R1_selector_socketpair`: `-3.1%`
- `R4_uvicorn_fastapi`: `-0.9%`

Conclusion:

- safe
- still too small by itself

### `C5` `_run_once` local-binding rewrite

This looked attractive on paper but was not borne out:

- `R2_asyncio_echo`: `+7.6%` regression
- `R3_uvicorn_plain`: `+0.2%`
- `R4_uvicorn_fastapi`: `-0.4%`

Conclusion:

- do not pursue

### `C6` `_process_events` exact-mask fast path

Very small and mixed:

- `R2_asyncio_echo`: effectively flat
- `R4_uvicorn_fastapi`: `-0.5%`
- `R3_uvicorn_plain`: `+0.3%`

Conclusion:

- too small to matter

### `C7` `EpollSelector.select` exact-event fast path

This was the best remaining simple candidate.

Exploratory run (5 samples):

- `R1_selector_socketpair`: `-3.6%`
- `R2_asyncio_echo`: `-2.6%`
- `R4_uvicorn_fastapi`: `-1.2%`
- `R3_uvicorn_plain`: `+0.4%`

Confirmatory run (7 samples):

- `R1_selector_socketpair`: `-4.1%`
- `R2_asyncio_echo`: `-3.2%`
- `R4_uvicorn_fastapi`: `-0.2%`
- `R3_uvicorn_plain`: `+0.2%`

Validation:

- `test_asyncio`, `test_selectors`, `test_socket`, `test_heapq`: passed
- import smoke passed for `anyio`, `asgiref`, `uvicorn`, `starlette`,
  `fastapi`, `httpx`, `django`, `celery`, `gunicorn`,
  `prompt_toolkit`
- branch-local live-server smoke checks passed

Conclusion:

- semantically clean
- real gain is modest and mostly confined to selector / echo-style paths
- not strong enough to outrank the already-validated logging / AST /
  ABC work

### `C8` / `C9` combined patches

Both combined variants lost the clean signal:

- `C8` regressed `M3_cancelled_timer_cleanup` and was effectively flat
  on `R4_uvicorn_fastapi`
- `C9` preserved safety but only kept small selector/echo wins while
  losing clarity

Conclusion:

- the best tiny changes do not compose into a stronger branch result

## Final assessment

This branch is a **weak / negative result**, not a filing candidate.

The important conclusions are:

- the event-loop hotspots are real, but the service-facing wins from
  small pure-Python rewrites are small
- `_run_once` local-binding cleanup is not the lever here
- the most credible tiny patch is in `EpollSelector.select`, not
  `base_events._run_once`
- if `asyncio` is revisited, the next serious step should be a deeper
  C-level or protocol-level experiment, not another round of local
  Python rewrites

## Recommendation

Do **not** prioritize a PR from this branch.

If we revisit `asyncio`, the best preserved idea is:

- `C7`: `EpollSelector.select` exact-event fast path

But even that should be treated as a low-priority follow-up, not the
next filing candidate.

## Artifacts

Branch-local artifacts live in `Misc/asyncio-eventloop-perf-data/`:

- `asyncio_eventloop_usage_scan.py`
- `asyncio_eventloop_bench.py`
- `asyncio_eventloop_checks.py`
- `usage-scan.json`
- `baseline.json`
- candidate outputs:
  - `c1_timerhandle_lt_exact_fastpath.json`
  - `c2_timerhandle_compare_family_exact_fastpath.json`
  - `c3_handle_direct_debug_attr.json`
  - `c4_call_site_debug_guard.json`
  - `c5_run_once_locals.json`
  - `c6_process_events_exact_masks.json`
  - `c7_epollselector_exact_masks.json`
  - `c7_epollselector_exact_masks_confirm.json`
  - `c8_combined_python_hotpaths.json`
  - `c9_combined_no_timer_lt.json`
  - `c1_timerhandle_lt_exact_fastpath_confirm.json`
