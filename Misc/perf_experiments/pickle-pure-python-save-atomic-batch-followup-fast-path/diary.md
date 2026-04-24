# pickle pure-Python save atomic batch follow-up fast path

Branch: `exp-pickle/save-atomic-followup-mainline`
Base commit: `b76535a0ca8`
Manifest: `Misc/perf_experiments/pickle-pure-python-save-atomic-batch-followup-fast-path/experiment.json`

## Goal

Archetype: `exact-type gate` plus `common-case split`.

The previous clean pickle save family already specialized exact-`int` list
batch appends inside `_batch_appends_exact()`, but the save-side profile still
showed broad `save_list()` traffic. The next incremental hypothesis was that
homogeneous exact `bool`, exact `str`, and exact `bytes` lists still paid
avoidable per-item `save()` dispatch even on the exact `_Pickler` path.

## Targets

- `Lib/pickle.py:1099 save_list`
- `Lib/pickle.py:1107 _batch_appends_exact`
- `Lib/pickle.py:562 Pickler.save`

## Success Criteria

- Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload
  reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked
  winner branch.

## Input Evidence

- Profiles:
  - inherited save-side signal from the prior pickle family:
    - `Lib/pickle.py:581 save`: about `5.501s` cumulative
    - `Lib/pickle.py:1087 save_list`: about `4.043s`
    - `Lib/pickle.py:1107 _batch_appends_exact`: still worth re-checking after
      the exact-`int` landing because only one atomic type had been specialized
- Usage scan:
  - this is an explicitly incremental family based on
    `exp-pickle/save-mainline` at `b76535a0ca8`, because that branch already
    contains `_batch_appends_exact()` and the earlier exact-`int` fast path
  - untouched homogeneous atomic shapes after that landing were:
    - exact `bool` lists
    - exact `str` lists
    - exact `bytes` lists
- Initial benchmark corpus:
  - `benchmarks/bench_pickle_pure_save_atomic_followup.py`
  - cases:
    - `S1_list_of_ints_10k_dump`
    - `S2_list_of_strs_1k_dump`
    - `S3_list_of_bytes_1k_dump`
    - `S4_nested_list_of_dicts_dump`
    - `S5_deep_list_dump`
    - `S6_mixed_scalar_list_dump`
    - `S7_bool_list_dump`
    - `S8_small_int_run_dump`
  - result artifacts:
    - `benchmarks/results/runtime-baseline-short.json`
    - `benchmarks/results/runtime-exact_bool_lists-short.json`
    - `benchmarks/results/runtime-exact_str_lists-short.json`
    - `benchmarks/results/runtime-exact_bytes_lists-short.json`
    - `benchmarks/results/runtime-exact_atomic_lists-short.json`
    - `benchmarks/results/source-baseline.json`
    - `benchmarks/results/source-candidate.json`
- Guardrails:
  - `guardrails/check_pickle_pure_save_atomic_followup_semantics.py`
  - result: passed (`pickle pure save atomic follow-up guardrails: ok`)

## Candidate Ledger

### E1

Status: rejected.

Thesis:

- Specialize only homogeneous exact `bool` lists inside
  `_batch_appends_exact()`.

Result:

- Runtime screen only:
  - geomean: about `+9.71%`
  - strongest case:
    - `S7_bool_list_dump`: `+97.91%`
  - but broad collateral movement was mixed:
    - `S1_list_of_ints_10k_dump`: `-2.46%`
    - `S2_list_of_strs_1k_dump`: `-1.88%`
    - `S3_list_of_bytes_1k_dump`: `-2.80%`

Decision:

- Rejected as a standalone landing shape. The target case was huge, but the
  isolated bool-only form was too mixed for the total gain.

### E2

Status: rejected.

Thesis:

- Specialize only homogeneous exact `str` lists.

Result:

- Runtime screen only:
  - geomean: about `+4.65%`
  - strongest case:
    - `S2_list_of_strs_1k_dump`: `+32.23%`

Decision:

- Rejected as a standalone landing shape. Positive, but too narrow compared to
  the combined atomic candidate.

### E3

Status: rejected.

Thesis:

- Specialize only homogeneous exact `bytes` lists.

Result:

- Runtime screen only:
  - geomean: about `+6.15%`
  - strongest case:
    - `S3_list_of_bytes_1k_dump`: `+35.92%`

Decision:

- Rejected as a standalone landing shape. Same story as `E2`: real, but less
  compelling than the combined atomic specialization.

### E4

Status: accepted and stacked.

Thesis:

- Extend `_batch_appends_exact()` to cover homogeneous exact `bool`,
  `str`, and `bytes` lists in addition to the already-landed exact-`int`
  path, keeping the same exact `_Pickler` guard and the same per-batch
  snapshot behavior.

Result:

- Runtime screen on `cpython-pickle-save-mainline`:
  - geomean: about `+18.87%`
  - details:
    - `S1_list_of_ints_10k_dump`: `+0.77%`
    - `S2_list_of_strs_1k_dump`: `+31.67%`
    - `S3_list_of_bytes_1k_dump`: `+36.91%`
    - `S4_nested_list_of_dicts_dump`: `+0.81%`
    - `S5_deep_list_dump`: `-2.56%`
    - `S6_mixed_scalar_list_dump`: `+4.70%`
    - `S7_bool_list_dump`: `+97.55%`
    - `S8_small_int_run_dump`: `+7.99%`
- Clean same-worktree source proof on
  `exp-pickle/save-atomic-followup-mainline`:
  - geomean: about `+17.34%`
  - details:
    - `S1_list_of_ints_10k_dump`: `-1.14%`
    - `S2_list_of_strs_1k_dump`: `+31.59%`
    - `S3_list_of_bytes_1k_dump`: `+37.56%`
    - `S4_nested_list_of_dicts_dump`: `+1.05%`
    - `S5_deep_list_dump`: `+0.22%`
    - `S6_mixed_scalar_list_dump`: `-1.17%`
    - `S7_bool_list_dump`: `+98.08%`
    - `S8_small_int_run_dump`: `+1.28%`

Decision:

- Accept.
- The combined atomic shape kept almost all of the runtime headroom at source
  level and stayed broad enough to justify promotion.

## Validation

- Guardrails:
  - runtime guardrail: passed
- Focused tests:
  - clean branch:
    - `test_pickle test_picklebuffer test_pickletools`: passed
    - `test_copy test_copyreg`: passed
    - `test_shelve`: passed
  - stacked branch:
    - `test_pickle test_picklebuffer test_pickletools`: passed
    - `test_copy test_copyreg`: passed
    - `test_shelve`: passed
- Full suite:
  - clean branch:
    - `49,892` run
    - `2,623` skipped
    - `SUCCESS` in `4 min 22 sec`
  - stacked branch:
    - `49,892` run
    - `2,620` skipped
    - `SUCCESS` in `4 min 18 sec`
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: accepted and stacked
- Accepted commit: `5d226b57ffc`
- Stacked winner commit: `62ad98219a6`

## Notes

- The important process lesson is that this family had to start from the
  earlier clean pickle save branch, not from bare root `main`, because
  `_batch_appends_exact()` itself is part of the prior accepted save-side
  winner set.
- The incremental shape is still reviewable because it does not widen the
  dispatch surface; it only extends the existing exact `_Pickler` binary-list
  fast path to more homogeneous exact atomic types.
