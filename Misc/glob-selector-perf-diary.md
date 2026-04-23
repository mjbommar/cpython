# Glob selector perf diary

Date: `2026-04-23`
Branch: `exp-glob/selectors-mainline`

## Goal

Evaluate the still-open glob tracker item:

- `Lib/glob.py:343` `_GlobberBase` selector closures
- `Lib/glob.py:537` `_StringGlobber`

The original tracker item came from the full-suite profile, where the
hot path was the `pathlib` selector stack, not the legacy
`glob.glob()` helpers. The first thing this branch needed to do was
correct the benchmark target before making any code changes.

## Harness

Added:

- `Misc/glob-selector-perf-data/glob_selector_bench.py`
- `Misc/glob-selector-perf-data/guardrails.py`

Final harness shape:

- `G1_flat_star`: `Path.glob("*")`
- `G2_flat_py`: `Path.glob("*.py")`
- `G3_tree_py_recursive`: `Path.rglob("*.py")`
- `G4_tree_literal`: `Path.glob("pkg7/subpkg/*.py")`
- `G5_deep_target_recursive`: `Path.rglob("target*.py")`

Guardrails confirm `pathlib` semantics, including hidden-file matching.

## Profiling findings

The original `glob.glob()` microbench was wrong for this tracker item.
When profiled, it was dominated by:

- `glob._iglob`
- `glob._iterdir`
- `glob._listdir`
- `fnmatch.filter`
- `posixpath.join`

The corrected `Path.glob()` / `Path.rglob()` profile instead showed the
real hot path:

- `Lib/glob.py:443` `select_wildcard()`
- `Lib/glob.py:486` `select_recursive()`
- `Lib/glob.py:495` `select_recursive_step()`
- `Lib/glob.py:543` `_StringGlobber.scandir()`
- `Lib/pathlib/__init__.py:278` `_from_parsed_string()`

Conclusion: selector construction itself was not the main issue. The
best low-risk target was filesystem entry iteration inside
`_StringGlobber.scandir()`.

## Candidate history

### Rejected direction: change the entry contract

I first changed `_GlobberBase` to consume raw entry objects instead of
the historical `(entry, name, path)` tuples. That sped up the concrete
filesystem `pathlib` path, but it broke `test_pathlib` because
`Lib/pathlib/types.py:_PathGlobber` and `zipfile.Path` still depended on
the tuple-shaped contract.

I then repaired that with a generic `entry_name()` / `entry_path()` /
`entry_is_dir()` abstraction. That restored correctness, but it erased
too much of the win. The exact final-patch benchmark for that variant
fell too close to noise, so I rejected it.

Lesson:

- do not widen the abstraction here unless there is a much larger payoff
- `glob.py` has multiple path-provider clients, not just real
  filesystem `DirEntry`

### Accepted direction: keep the contract, remove generator churn

The accepted patch is much smaller:

- keep the historical `(entry, name, path)` tuple contract
- change `_StringGlobber.scandir()` from:
  - `list(scandir_it)` plus a generator expression over `(entry, name, path)`
- to:
  - a direct list comprehension that materializes the tuple list inside
    the `os.scandir()` context

Patch:

- `Lib/glob.py`

```python
with os.scandir(path) as scandir_it:
    return [(entry, entry.name, entry.path) for entry in scandir_it]
```

This preserves semantics for all existing `_GlobberBase` consumers while
removing one generator layer and repeated tuple assembly outside the
`scandir` context.

## Benchmark results

Final exact-patch runs:

Run 1 (`baseline3` vs `candidate5`)

- `G1_flat_star`: `0.268684s -> 0.266657s` (`+0.76%`)
- `G2_flat_py`: `0.247558s -> 0.240463s` (`+2.95%`)
- `G3_tree_py_recursive`: `0.253990s -> 0.245256s` (`+3.56%`)
- `G4_tree_literal`: `0.046916s -> 0.047324s` (`-0.86%`)
- `G5_deep_target_recursive`: `0.273191s -> 0.261091s` (`+4.63%`)
- geomean: `+2.19%`

Run 2 (`baseline4` vs `candidate6`)

- `G1_flat_star`: `0.553626s -> 0.544949s` (`+1.59%`)
- `G2_flat_py`: `0.493760s -> 0.486436s` (`+1.51%`)
- `G3_tree_py_recursive`: `0.517092s -> 0.497932s` (`+3.85%`)
- `G4_tree_literal`: `0.097312s -> 0.095755s` (`+1.63%`)
- `G5_deep_target_recursive`: `0.562802s -> 0.529668s` (`+6.26%`)
- geomean: `+2.95%`

Two-run average:

- `G1_flat_star`: `+1.32%`
- `G2_flat_py`: `+1.98%`
- `G3_tree_py_recursive`: `+3.75%`
- `G4_tree_literal`: `+0.80%`
- `G5_deep_target_recursive`: `+5.72%`
- geomean: `+2.70%`

Interpretation:

- the win is real but modest
- recursive selector cases benefit the most
- the patch is small enough and safe enough that this still clears the
  accept bar

## Validation

Focused checks:

- custom guardrails: passed
- `./python -m test test_glob test_pathlib`: passed

Clean-mainline full suite:

- `49,882` tests run
- `2,624` skipped
- `SUCCESS` in `4 min 31 sec`

## Decision

Accepted.

Reason:

- profile-targeted
- semantics-preserving
- measurable win on the right `pathlib` path
- full clean-mainline suite green
