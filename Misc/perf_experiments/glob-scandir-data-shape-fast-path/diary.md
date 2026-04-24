# glob scandir data shape fast path

Branch: `exp-glob/scandir-shape-mainline`
Base commit: `87ee575bbd162f4f68b6ea5534b510734ea73ef2`
Manifest: `Misc/perf_experiments/glob-scandir-data-shape-fast-path/experiment.json`

## Goal

Archetype: `allocator / accumulator refactor` plus `common-case split`.
The rejected `glob-recursive-selector-fast-path` family proved that more
closure surgery in `recursive_selector()` was not enough. The remaining
reopen hypothesis was narrower and lower-level: `_StringGlobber.scandir()`
still paid for a `list(os.scandir(...))` plus per-entry `(entry, name, path)`
tuple materialization, and the generic `_GlobberBase` selector loops then
unpacked those tuples even on string-path workloads that could iterate raw
`DirEntry` objects directly.

## Targets

- `Lib/glob.py:445 _GlobberBase.wildcard_selector`
- `Lib/glob.py:486 _GlobberBase.recursive_selector`
- `Lib/glob.py:543 _StringGlobber.scandir`

## Success Criteria

- Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload
  reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked
  winner branch.

## Input Evidence

- Profiles:
  - inherited reopen signal from the rejected recursive-selector family:
    - `Lib/glob.py:486 select_recursive`: about `0.926s` cumulative
    - `Lib/glob.py:495 select_recursive_step`: about `0.852s`
    - `Lib/glob.py:543 scandir`: about `0.776s`
    - `Lib/pathlib/__init__.py:1106 walk`: about `0.511s`
- Usage scan:
  - `_StringGlobber` is the shared string-path glob engine for both
    `glob.[i]glob()` and `pathlib.Path.glob()/rglob()`
  - the reopen is materially different from the rejected family:
    this one targets `scandir()` data shape and selector tuple churn, not
    `recursive_selector()` closure structure
  - `pathlib.Path.walk()` was re-reviewed and left deprioritized as a thin
    wrapper over `os.walk()`
- Initial benchmark corpus:
  - `benchmarks/bench_glob_scandir_shape.py`
  - cases:
    - `G1_glob_recursive_all`
    - `G2_glob_recursive_py`
    - `G3_pathlib_rglob_all`
    - `G4_pathlib_glob_recursive_all`
    - `G5_pathlib_glob_recursive_py`
    - `G6_glob_wildcard_all`
    - `G7_glob_wildcard_py`
    - `G8_pathlib_glob_wildcard_all`
  - result artifacts:
    - `benchmarks/results/runtime-baseline.json`
    - `benchmarks/results/runtime-recursive-only.json`
    - `benchmarks/results/runtime-both-selectors.json`
    - `benchmarks/results/source-baseline.json`
    - `benchmarks/results/source-candidate.json`
    - `benchmarks/results/source-baseline-b.json`
    - `benchmarks/results/source-candidate-b.json`
- Guardrails:
  - `guardrails/check_glob_scandir_shape_semantics.py`
  - result: passed (`glob scandir shape guardrails: ok`)

## Candidate Ledger

### E1

Status: rejected.

Thesis:

- Specialize only the recursive string-path selector to iterate raw
  `DirEntry` lists directly, leaving wildcard expansion on the old generic
  tuple path.

Result:

- Runtime proof only: about `+1.65%` geomean.
- Details:
  - `G1_glob_recursive_all`: `+2.25%`
  - `G2_glob_recursive_py`: `+2.93%`
  - `G3_pathlib_rglob_all`: `+4.43%`
  - `G4_pathlib_glob_recursive_all`: `+4.77%`
  - `G5_pathlib_glob_recursive_py`: `+5.07%`
  - `G6_glob_wildcard_all`: `-7.26%`
  - `G7_glob_wildcard_py`: `+1.64%`
  - `G8_pathlib_glob_wildcard_all`: `-0.07%`

Decision:

- Rejected as a standalone landing shape. Recursive cases were positive,
  but leaving wildcard expansion on the old path created too much mixed
  behavior for too little total gain.

### E2

Status: accepted and stacked.

Thesis:

- Specialize both string-path selectors and add a raw-entry helper:
  `_StringGlobber` should iterate `DirEntry` lists directly for recursive
  and wildcard expansion, reading `entry.name` and `entry.path` only when
  needed, while preserving the old generic `_GlobberBase` path.

Result:

- Runtime proof: about `+3.94%` geomean.
- Runtime details:
  - `G1_glob_recursive_all`: `+0.91%`
  - `G2_glob_recursive_py`: `+2.46%`
  - `G3_pathlib_rglob_all`: `+7.31%`
  - `G4_pathlib_glob_recursive_all`: `+6.66%`
  - `G5_pathlib_glob_recursive_py`: `+9.11%`
  - `G6_glob_wildcard_all`: `-1.02%`
  - `G7_glob_wildcard_py`: `+2.73%`
  - `G8_pathlib_glob_wildcard_all`: `+3.77%`
- Same-worktree source proof on `exp-glob/scandir-shape-mainline`:
  - first pass geomean: about `+2.33%`
  - second pass geomean: about `+2.20%`
  - two-pass average geomean: about `+2.27%`
- Average source details:
  - `G1_glob_recursive_all`: `+1.99%`
  - `G2_glob_recursive_py`: `+1.25%`
  - `G3_pathlib_rglob_all`: `+3.75%`
  - `G4_pathlib_glob_recursive_all`: `+4.67%`
  - `G5_pathlib_glob_recursive_py`: `+4.19%`
  - `G6_glob_wildcard_all`: `+0.90%`
  - `G7_glob_wildcard_py`: `+2.15%`
  - `G8_pathlib_glob_wildcard_all`: `-0.59%`

Decision:

- Accepted. The win shrank from runtime proof to source proof, but it
  stayed broad, reviewable, and clearly positive on the recursive/pathlib
  workloads that motivated the family.

## Validation

- Guardrails:
  - runtime guardrail: passed
- Focused tests:
  - clean branch `exp-glob/scandir-shape-mainline`:
    - `test_glob`: passed
    - `test_pathlib`: passed
  - stacked branch `exp-combined-winners-local`:
    - `test_glob`: passed
    - `test_pathlib`: passed
- Full suite:
  - clean branch:
    - `49,882` run
    - `2,623` skipped
    - `SUCCESS` in `4 min 20 sec`
  - stacked branch:
    - `49,892` run
    - `2,620` skipped
    - `SUCCESS` in `4 min 20 sec`
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: accepted and stacked
- Accepted commit: `2a873925d43`
- Stacked winner commit: `4537fd42930`

## Notes

- The reopen thesis was right: `glob` still had leverage, but it was in
  `scandir()` data shape and selector tuple churn, not in more generator
  reshaping inside `recursive_selector()`.
- Keeping the change string-specific mattered. The generic `_GlobberBase`
  code stayed untouched, which kept the review surface small and avoided
  creating a new abstraction branch for non-string path kinds.
- The stacked cherry-pick revealed an existing glob-layer winner already in
  `exp-combined-winners-local`: commit `a0a9f825350`
  (`perf: speed up pathlib glob scandir tuples`). The correct merge was to
  keep that tuple-list `scandir()` behavior and add this raw-entry selector
  specialization underneath it, rather than replacing the earlier win.
