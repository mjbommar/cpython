# `_pickle` dump/load wrapper perf diary

Branch: `exp-pickle/wrapper-mainline`
Worktree: `/home/mjbommar/projects/personal/cpython-pickle-wrapper-mainline`

## Goal

Investigate the remaining top-25 `_pickle` entries:

- `Modules/_pickle.c:4835` `_pickle_Pickler_dump_impl()`
- `Modules/_pickle.c:7239` `_pickle_Unpickler_load_impl()`

The intent is to target common exact-type `Pickler.dump()` /
`Unpickler.load()` traffic without changing pickle bytes, memo behavior,
or subclass-visible hook semantics.

## Harness

Added:

- `Misc/pickle-wrapper-perf-data/pickle_wrapper_bench.py`
- `Misc/pickle-wrapper-perf-data/guardrails.py`

Benchmark scenarios:

- `P1_dump_none_exact`
- `P2_dump_small_list_exact`
- `P3_dump_nested_exact`
- `P4_load_none_exact`
- `P5_load_small_list_exact`
- `P6_load_nested_exact`

Guardrails cover:

- exact `Pickler` instance `persistent_id` override
- exact `Unpickler` default persistent-id error text
- exact `Unpickler` instance `persistent_load` override
- subclass `Unpickler.persistent_load` override

## Experiment Log

### E1 — exact-type hook fast paths

Status: in progress.

Thesis:

- `dump()` already recognizes the default `persistent_id` method after
  `PyObject_GetAttr()`, but still pays for the attribute lookup and bound
  method creation on exact built-in `Pickler` objects
- `load()` always resolves `persistent_load` up front even though most
  pickles never use persistent-id opcodes
- exact built-in `Pickler` / `Unpickler` instances have a lower-risk fast
  path because the type is immutable and the code already tracks explicit
  instance overrides in `persistent_id_attr` / `persistent_load_attr`

Candidate patch shape:

- skip `persistent_id` attribute lookup on exact `Pickler` when
  `persistent_id_attr == NULL`
- skip `reducer_override` lookup on exact `Pickler`
- skip `persistent_load` lookup on exact `Unpickler` when
  `persistent_load_attr == NULL`
- make `load_persid` / `load_binpersid` raise the same
  `UnpicklingError` directly when `self->persistent_load == NULL`

Result:

- accepted after same-worktree A/B validation and full-suite green

Implementation details:

- `dump()` now mirrors the existing persistent-id skip logic earlier for
  the exact built-in `Pickler` case:
  - exact `Pickler` + no instance `persistent_id` override:
    `self->persistent_id = NULL`
  - exact `Pickler`:
    `self->reducer_override = NULL`
  - subclasses still use the original dynamic lookup path
- `load()` now mirrors that shape for exact built-in `Unpickler`:
  - exact `Unpickler` + no instance `persistent_load` override:
    `self->persistent_load = NULL`
  - subclasses still use the original dynamic lookup path
- `load_persid()` / `load_binpersid()` now raise the same
  `UnpicklingError` directly when `self->persistent_load == NULL`

Methodology note:

- an initial baseline taken against a separately built `main` binary
  looked implausibly large
- the accepted numbers below come only from a stricter same-worktree
  A/B process:
  1. patch applied
  2. save patch to `/tmp/pickle-wrapper-e1.patch`
  3. `git apply -R` to restore clean baseline in the same worktree
  4. rebuild `_pickle`
  5. benchmark baseline
  6. reapply the exact same patch
  7. rebuild `_pickle`
  8. benchmark candidate
- that cycle was run twice

Targeted exact-type panel:

- pair 1:
  - `P1_dump_none_exact`: `+118.08%`
  - `P2_dump_small_list_exact`: `+65.30%`
  - `P3_dump_nested_exact`: `+9.20%`
  - `P4_load_none_exact`: `+21.10%`
  - `P5_load_small_list_exact`: `+7.03%`
  - `P6_load_nested_exact`: `-1.96%`
  - geometric mean: `+30.78%`
- pair 2:
  - `P1_dump_none_exact`: `+116.10%`
  - `P2_dump_small_list_exact`: `+64.69%`
  - `P3_dump_nested_exact`: `+5.15%`
  - `P4_load_none_exact`: `+15.11%`
  - `P5_load_small_list_exact`: `+6.03%`
  - `P6_load_nested_exact`: `-0.09%`
  - geometric mean: `+28.79%`
- two-run average:
  - `P1_dump_none_exact`: `+117.09%`
  - `P2_dump_small_list_exact`: `+64.99%`
  - `P3_dump_nested_exact`: `+7.18%`
  - `P4_load_none_exact`: `+18.10%`
  - `P5_load_small_list_exact`: `+6.53%`
  - `P6_load_nested_exact`: `-1.03%`
  - geometric mean: `+29.79%`

Broader mixed-stream panel:

- reproducible harness added as
  `Misc/pickle-wrapper-perf-data/stream_mixed_bench.py`
- same-worktree A/B result:
  - `B1_dump_stream_mixed_exact`: `+91.61%`
  - `B2_load_stream_mixed_exact`: `+3.56%`
  - `B3_roundtrip_stream_mixed_exact`: `+33.65%`
  - geometric mean: `+38.42%`

Correctness and validation:

- custom guardrails passed on both baseline and candidate builds
- focused suites passed:
  - `test_pickle`
  - `test_picklebuffer`
  - `test_copy`
  - `test_copyreg`
  - `test_shelve`
  - `test_multiprocessing_spawn`
  - result: `2,047` tests run, `129` skipped, `SUCCESS` in
    `1 min 33 sec`
- clean-branch full suite passed:
  - `49,882` tests run
  - `2,603` skipped
  - `491/502` files run
  - `SUCCESS` in `4 min 32 sec`

What we learned:

- the wrapper lines in the top-25 profile were not a red herring: a
  large part of the visible cost for exact built-in `Pickler.dump()` /
  `Unpickler.load()` really was repeated hook lookup work
- exact-type specialization is the right level here; subclasses keep the
  dynamic path and their override semantics unchanged
- `persistent_load` is especially worth handling lazily because most
  real pickles never use persistent-id opcodes, so the old unconditional
  method resolution was pure overhead on the common path
