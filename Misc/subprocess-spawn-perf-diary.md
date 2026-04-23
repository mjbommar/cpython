# Subprocess spawn perf diary

Date: `2026-04-23`
Branch: `exp-subprocess/spawn-mainline`

## Goal

Evaluate the still-open subprocess tracker items:

- `Lib/subprocess.py:1879` `Popen._execute_child()`
- `Lib/subprocess.py:1839` `Popen._posix_spawn()`

## Harness

Added:

- `Misc/subprocess-spawn-perf-data/guardrails.py`
- `Misc/subprocess-spawn-perf-data/subprocess_spawn_bench.py`

The benchmark uses a mocked `os.posix_spawn()` and dummy `Popen`
instances so it measures Python-side setup overhead, not kernel process
creation time.

## Profiling findings

Initial direct profiling of the helpers showed two clear costs:

- `Popen._execute_child()` spent a large share of its Python time in
  `os.path.dirname(executable)` inside the POSIX-spawn fast-path gate.
- `Popen._posix_spawn()` spent a large share of its Python time in
  `_close_pipe_fds()`, especially when the common path had no actual
  descriptors to close and still built an empty `ExitStack`.

That suggested three safe, local optimizations:

1. cache the `setsigdef` list once per process instead of rebuilding it
   on every `_posix_spawn()`
2. add a no-op fast path in `_close_pipe_fds()` for the common
   no-pipe/no-devnull case
3. avoid `os.path.dirname()` for exact `str` / `bytes` executables in
   `_execute_child()` and use a cheap `"/" in executable` test instead

## Accepted patch

Files changed:

- `Lib/subprocess.py`

Summary:

- added `_POSIX_SPAWN_SETSIGDEF = _get_posix_spawn_setsigdef()`
- `_posix_spawn()` now reuses that cached list
- `_close_pipe_fds()` now returns immediately when there is nothing to
  close on the POSIX common path
- `_execute_child()` now uses a cheap exact-`str` / exact-`bytes`
  directory check before falling back to `os.path.dirname()` for other
  path-like objects

## Guardrails

Custom guardrails passed:

- `posix_spawn_restore_signals`
- `posix_spawn_no_file_actions`
- `close_pipe_fds_fast_noop`
- `posix_spawn_file_actions`
- `execute_child_fast_path_args`
- `execute_child_fast_path_exec`

## Benchmark results

Run 1 (`baseline` vs `candidate`)

- `S1_posix_spawn_common`: `0.098743s -> 0.054115s` (`+82.47%`)
- `S2_posix_spawn_pipe_actions`: `0.243220s -> 0.237286s` (`+2.50%`)
- `S3_execute_child_common_str`: `0.094285s -> 0.072522s` (`+30.01%`)
- `S4_execute_child_common_bytes`: `0.092977s -> 0.092368s` (`+0.66%`)
- geomean: `+25.08%`

Run 2 (`baseline2` vs `candidate2`)

- `S1_posix_spawn_common`: `0.048569s -> 0.026614s` (`+82.49%`)
- `S2_posix_spawn_pipe_actions`: `0.119476s -> 0.114692s` (`+4.17%`)
- `S3_execute_child_common_str`: `0.045451s -> 0.036838s` (`+23.38%`)
- `S4_execute_child_common_bytes`: `0.045490s -> 0.045023s` (`+1.04%`)
- geomean: `+24.07%`

Two-run average:

- `S1_posix_spawn_common`: `+82.48%`
- `S2_posix_spawn_pipe_actions`: `+3.05%`
- `S3_execute_child_common_str`: `+27.78%`
- `S4_execute_child_common_bytes`: `+0.78%`
- geomean: `+24.74%`

Interpretation:

- the no-pipe POSIX-spawn path is the clear winner
- exact-`str` executable handling in `_execute_child()` is also worth it
- exact-`bytes` executables move only slightly, which is fine because
  they stay correct and do not regress
- pipe-heavy `_posix_spawn()` setups still improve, but only modestly

## Validation

Focused tests:

- `test_subprocess`: passed
- `test_subprocess test_multiprocessing_spawn test_multiprocessing_fork`
  `test_multiprocessing_forkserver test.test_asyncio.test_subprocess`:
  `1,794` tests, `244` skipped, `SUCCESS` in `4 min 56 sec`

Clean-mainline full suite:

- `49,882` tests run
- `2,623` skipped
- `SUCCESS` in `4 min 30 sec`

## Decision

Accepted.

What we learned:

- the subprocess top-25 item was not mostly about repeated
  `_use_posix_spawn()` feature detection; upstream had already cached
  that
- the remaining Python-side overhead on POSIX is concentrated in small
  helper work after that decision has already been made
- the best wins here came from common-case no-op elimination and exact
  type specialization, not from broad control-flow rewrites
