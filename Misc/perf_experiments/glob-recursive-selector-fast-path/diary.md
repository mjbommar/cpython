# glob recursive selector fast path

Branch: `exp-glob/recursive-selector-mainline`
Base commit: `5a37cb8a24363a730302031721baeb264aff1a49`
Manifest: `Misc/perf_experiments/glob-recursive-selector-fast-path/experiment.json`

## Goal

Archetype: `common-case split` plus `control-flow lifting`. Fresh stacked
discovery still showed a real recursive glob cluster in `Lib/glob.py` and
adjacent `pathlib` usage. The initial hypothesis was that the dominant `**`
recursive path often has `match is None`, yet `select_recursive_step()`
unconditionally computes `stringify_path(entry_path)` before checking that.

## Targets

- `Lib/glob.py:486 select_recursive`
- `Lib/glob.py:495 select_recursive_step`
- `Lib/glob.py:543 scandir`

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
    - `Lib/glob.py:486 select_recursive`: about `0.926s` cumulative
    - `Lib/glob.py:495 select_recursive_step`: about `0.852s`
    - `Lib/glob.py:543 scandir`: about `0.776s`
    - `Lib/pathlib/__init__.py:1106 walk`: about `0.511s`
- Usage scan:
  - the recursive glob signal is real and not just a syscall leaf:
    - `select_recursive` and `select_recursive_step` both carry substantial
      Python cumulative time
    - the adjacent `pathlib` traffic comes through the same globbing stack
  - `pathlib.walk()` was reviewed but deprioritized as a likely thinner wrapper
    over `os.walk()` than the recursive selector machinery
- Initial benchmark corpus:
  - `benchmarks/bench_glob_recursive_selector.py`
  - cases:
    - `G1_glob_recursive_all`
    - `G2_glob_recursive_py`
    - `G3_pathlib_rglob_all`
    - `G4_pathlib_glob_recursive_all`
    - `G5_pathlib_glob_recursive_py`
  - result artifacts:
    - `benchmarks/results/runtime-baseline.json`
    - `benchmarks/results/runtime-lazy-stringify.json`
    - `benchmarks/results/runtime-baseline-b.json`
    - `benchmarks/results/runtime-inline-step.json`
- Guardrails:
  - `guardrails/check_glob_recursive_selector_semantics.py`
  - result: passed (`glob recursive selector guardrails: ok`)

## Candidate Ledger

### E1

Status: rejected.

Thesis:

Defer `stringify_path(entry_path)` until `match is not None`, since the common
recursive `**` path often does not need it.

Result:

- Runtime proof only: about `+0.93%` geomean.
- Details:
  - `G1_glob_recursive_all`: `+1.08%`
  - `G2_glob_recursive_py`: `+0.61%`
  - `G3_pathlib_rglob_all`: `+0.65%`
  - `G4_pathlib_glob_recursive_all`: `+0.98%`
  - `G5_pathlib_glob_recursive_py`: `+1.31%`

Decision:

Rejected before source work. The win was too small to justify a clean branch.

### E2

Status: rejected.

Thesis:

Inline `select_recursive_step()` into the outer loop and keep the lazy
`stringify_path()` change, to reduce nested generator overhead in addition to
the redundant path-string conversion.

Result:

- Runtime proof only: about `-0.47%` geomean.
- Details:
  - `G1_glob_recursive_all`: `-1.16%`
  - `G2_glob_recursive_py`: `-0.99%`
  - `G3_pathlib_rglob_all`: `+0.29%`
  - `G4_pathlib_glob_recursive_all`: `+0.20%`
  - `G5_pathlib_glob_recursive_py`: `-0.67%`

Decision:

Rejected before source work. The broader rewrite regressed the string `glob`
cases that motivated the family.

## Validation

- Guardrails:
  - runtime guardrail: passed
- Focused tests:
  - not run
- Full suite:
  - not run
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: rejected
- Accepted commit:
- Stacked winner commit:

## Notes

- The recursive glob signal is real, but these two reviewable Python-level
  shapes did not move enough work to survive the benchmark gate.
- If this family is ever reopened, the next probe should focus on the
  `scandir()` data shape and tuple materialization rather than more closure
  surgery in `recursive_selector()`.
