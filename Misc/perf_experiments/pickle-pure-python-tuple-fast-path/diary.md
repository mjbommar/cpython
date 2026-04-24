# pickle pure-Python tuple fast path

Branch: `exp-pickle/tuple-mainline`
Base commit: `fbfae49a64ac80563cc9eabef3d93fad3c44ac8f`
Manifest: `Misc/perf_experiments/pickle-pure-python-tuple-fast-path/experiment.json`

## Goal

Archetype: exact-type gate plus common-case split. After the exact-list and
exact-int batch winners, pure-Python pickle save-side cost still clusters in
`save_tuple()`. The likely leverage is a narrower exact `_Pickler` / exact
tuple common path that avoids generic per-element `save()` dispatch while
preserving recursive-tuple behavior and byte output.

## Targets

- `Lib/pickle.py:1028 save_tuple`
- `Lib/pickle.py:581 save`

## Success Criteria

- Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload
  reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked
  winner branch.

## Input Evidence

- Profiles:
  - `/tmp/stacked-discovery-2026-04-24.pstats`
  - stacked discovery attribution:
    - `Lib/pickle.py:581 save`: about `5.501s` cumulative
    - `Lib/pickle.py:1028 save_tuple`: about `3.559s`
    - `Lib/pickle.py:1087 save_list`: about `4.043s`
- Usage scan:
  - verified that the stacked baseline already includes the earlier
    pure-Python pickle save-side winner set plus the newer exact-int list batch
    specialization
  - re-read the old combined-winners pickle diary and explicitly rejected the
    older "skip memoize for atomic tuples" direction because it changes byte
    output and fixture expectations
  - the safe incremental shape is byte-stable exact `_Pickler` specialization
    for homogeneous exact-`int` tuples inside `save_tuple()`
- Initial benchmark corpus:
  - `T1_tuple_of_ints_10k_dump`
  - `T2_tuple_of_strs_1k_dump`
  - `T3_nested_tuple_dump`
  - `T4_mixed_scalar_tuple_dump`
  - `T5_small_int_tuple_dump`
  - `T6_int_pair_tuple_dump`
  - `T7_tuple_of_dicts_dump`
- Guardrails:
  - `check_pickle_pure_tuple_semantics.py`
  - verifies byte-for-byte identity against baseline for representative tuples
  - verifies roundtrip equality
  - verifies subclass fallback through `persistent_id`

## Candidate Ledger

### E1

Status: accepted.

Thesis:

- Specialize `save_tuple()` for exact `_Pickler` dumping homogeneous exact-int
  tuples, using direct `save_long()` dispatch while preserving the existing
  small-tuple opcodes, `MARK`/`TUPLE` behavior, memoization, and subclass
  override semantics.

Result:

- Runtime monkeypatch proof on stacked baseline:
  - `T1_tuple_of_ints_10k_dump`: `4915720.4 -> 3302767.1 ns` (`+48.84%`)
  - `T2_tuple_of_strs_1k_dump`: `+1.52%`
  - `T3_nested_tuple_dump`: `+21.17%`
  - `T4_mixed_scalar_tuple_dump`: `-3.41%`
  - `T5_small_int_tuple_dump`: `+65.38%`
  - `T6_int_pair_tuple_dump`: `+15.37%`
  - `T7_tuple_of_dicts_dump`: `+0.84%`
  - geomean: `1.191156x` (`+19.12%`)
- Clean same-worktree reduced source A/B:
  - `T1_tuple_of_ints_10k_dump`: `4931179.7 -> 3460068.4 ns` (`+42.52%`)
  - `T2_tuple_of_strs_1k_dump`: `+1.40%`
  - `T3_nested_tuple_dump`: `+21.43%`
  - `T4_mixed_scalar_tuple_dump`: `-0.64%`
  - `T5_small_int_tuple_dump`: `+71.64%`
  - `T6_int_pair_tuple_dump`: `+17.87%`
  - `T7_tuple_of_dicts_dump`: `-1.68%`
  - geomean: `1.194431x` (`+19.44%`)

Decision:

- Accept.
- The source-level result stayed essentially identical to the runtime proof,
  the guardrail confirmed byte stability, and the specialization boundary is
  narrow enough to avoid bypassing subclass hooks.

## Validation

- Focused tests:
  - clean guardrail:
    `check_pickle_pure_tuple_semantics.py`: `ok`
  - clean focused tests:
    `test_pickle test_picklebuffer test_pickletools`: passed
  - clean focused tests:
    `test_copy test_copyreg test_shelve`: passed
- Full suite:
  - clean branch: `49,892` run, `2,623` skipped, `SUCCESS` in `4 min 21 sec`
- Ecosystem / third-party:
- Stacked validation:
  - stacked guardrail:
    `check_pickle_pure_tuple_semantics.py`: `ok`
  - stacked focused tests:
    `test_pickle test_picklebuffer test_pickletools`: passed
  - stacked focused tests:
    `test_copy test_copyreg test_shelve`: passed
  - stacked branch: `49,892` run, `2,621` skipped, `SUCCESS` in
    `4 min 19 sec`

## Acceptance Decision

- Decision: accepted
- Accepted commit: `a521002acec`
- Stacked winner commit: `383516c4dfe`

## Notes

- The earlier "atomic tuple skip memoize" idea remains rejected because it is
  not byte-stable even if it benchmarks well.
- The winning shape is deliberately boring: exact `_Pickler`, exact `int`,
  unchanged opcodes, unchanged memoization, unchanged subclass fallbacks.
- Current phase: `stacked`
- Next gate: none; this family is fully promoted.
