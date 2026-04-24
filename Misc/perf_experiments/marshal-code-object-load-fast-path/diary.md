# marshal code-object load fast path

Branch: `exp-marshal/load-mainline`
Base commit: `b9f0f6309ec1ef08f3a73f7f01eeb12d824ceb23`
Manifest: `Misc/perf_experiments/marshal-code-object-load-fast-path/experiment.json`

## Goal

Archetype: `common-case split` plus `control-flow lifting`.

After the earlier importlib winners, the remaining `.pyc` path still depends on
`marshal.loads()` to decode code objects, with importlib immediately wrapping
that in `_compile_bytecode()`. This family is explicitly scoped to code-object
loads used by the import system, not to broad generic marshal rewrites.

## Targets

- `Python/marshal.c:1881 PyMarshal_ReadObjectFromString`
- `Lib/importlib/_bootstrap_external.py:500 _compile_bytecode`

## Success Criteria

- Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload
  reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked
  winner branch.

## Input Evidence

- Profiles:
  - this family comes from the top-ranked remaining deep-runtime list, not from
    a fresh Python-level leaf profile, because `marshal.c` does not surface well
    in ordinary `cProfile` output
- Usage scan:
  - `Lib/importlib/_bootstrap_external.py:_compile_bytecode()` calls
    `marshal.loads(data)` directly on the body of `.pyc` files
  - `Lib/zipimport.py` also calls `marshal.loads(data[16:])`
  - `Lib/modulefinder.py`, `Lib/pkgutil.py`, `Lib/pstats.py`, and `idlelib.rpc`
    also use marshal load paths, but the importlib/zipimport code-object path is
    the primary target here
  - `PyMarshal_ReadObjectFromString()` itself is very small and mostly sets up
    `RFILE`, so the next useful step is not random C surgery; it is identifying
    which code-object-heavy read shapes dominate after that setup
- Initial benchmark corpus:
  - `benchmarks/bench_marshal_code_load.py`
  - cases:
    - `M1_load_tiny`
    - `M2_load_nested`
    - `M3_load_many_consts`
    - `M4_load_class_methods`
    - `I1_compile_bytecode_tiny`
    - `I2_compile_bytecode_nested`
    - `I3_compile_bytecode_many_consts`
    - `I4_compile_bytecode_class_methods`
  - baseline artifact:
    - `benchmarks/results/runtime-baseline.json`
  - baseline means:
    - `M1_load_tiny`: about `892.6 ns`
    - `M2_load_nested`: about `1995.7 ns`
    - `M3_load_many_consts`: about `3790.0 ns`
    - `M4_load_class_methods`: about `3403.1 ns`
    - `I1_compile_bytecode_tiny`: about `1465.4 ns`
    - `I2_compile_bytecode_nested`: about `2422.7 ns`
    - `I3_compile_bytecode_many_consts`: about `4366.9 ns`
    - `I4_compile_bytecode_class_methods`: about `3948.3 ns`
- Guardrails:
  - `guardrails/check_marshal_code_load_semantics.py`
  - result: passed (`marshal code load guardrails: ok`)

## Candidate Ledger

### E1

Status: accepted on the clean branch.

Thesis:

`PyMarshal_ReadObjectFromString()` itself is only a tiny wrapper, but the
reference-list bookkeeping under `r_ref_reserve()` and `r_ref()` sits directly
on the code-object load path. The candidate is a narrow helper specialization:
replace generic `PyList_Append()` calls with `_PyList_AppendTakeRef()` and make
the ownership transfer explicit with `Py_NewRef(...)`.

Result:

- Clean source patch:
  - add `pycore_list.h`
  - `r_ref_reserve()`: append `Py_NewRef(Py_None)` via
    `_PyList_AppendTakeRef()`
  - `r_ref()`: append `Py_NewRef(o)` via `_PyList_AppendTakeRef()`
- Clean source baseline:
  - `M1_load_tiny`: about `954.2 ns`
  - `M2_load_nested`: about `2042.0 ns`
  - `M3_load_many_consts`: about `3881.6 ns`
  - `M4_load_class_methods`: about `3583.9 ns`
  - `I1_compile_bytecode_tiny`: about `1301.3 ns`
  - `I2_compile_bytecode_nested`: about `2539.9 ns`
  - `I3_compile_bytecode_many_consts`: about `4454.5 ns`
  - `I4_compile_bytecode_class_methods`: about `3986.1 ns`
- Clean source candidate:
  - `M1_load_tiny`: about `874.7 ns` (`+9.09%`)
  - `M2_load_nested`: about `1971.0 ns` (`+3.60%`)
  - `M3_load_many_consts`: about `3897.1 ns` (`-0.40%`)
  - `M4_load_class_methods`: about `3502.1 ns` (`+2.34%`)
  - `I1_compile_bytecode_tiny`: about `1273.5 ns` (`+2.18%`)
  - `I2_compile_bytecode_nested`: about `2387.0 ns` (`+6.41%`)
  - `I3_compile_bytecode_many_consts`: about `4416.3 ns` (`+0.86%`)
  - `I4_compile_bytecode_class_methods`: about `3824.0 ns` (`+4.24%`)
- Geomean:
  - about `+3.50%`
- Guardrail:
  - passed on the clean worktree

Implementation note:

The first proof attempt used `_PyList_AppendTakeRef(..., o)` directly in
`r_ref()`. That was wrong: `r_ref()` still returns `o` to the caller, so the
list append must consume a *new* reference, not the caller's ownership. That
mistake caused memory corruption during the freeze regeneration build step
(`malloc(): unaligned tcache chunk detected`). The corrected variant uses
`Py_NewRef(o)` and rebuilt cleanly.

Decision:

Accepted on the clean branch.

## Validation

- Guardrails:
  - runtime guardrail: passed
  - clean source guardrail: passed
  - stacked guardrail: passed
- Focused tests:
  - `test_marshal test_importlib test_zipimport`: passed
  - `test_pkgutil test_pstats test_modulefinder`: passed
  - stacked `test_marshal test_importlib test_zipimport`: passed
  - stacked `test_pkgutil test_pstats test_modulefinder`: passed
- Full suite:
  - clean branch full suite passed:
    - `49,882` run
    - `2,623` skipped
    - `SUCCESS` in `4 min 21 sec`
  - stacked branch full suite passed:
    - `49,892` run
    - `2,620` skipped
    - `SUCCESS` in `4 min 18 sec`
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: accepted and stacked
- Accepted commit: `24902c5e383`
- Stacked winner commit: `dfe1cfe4679`

## Notes

- Native `perf` attribution was blocked on this machine by
  `perf_event_paranoid=4`, so this family relied on static source inspection,
  targeted code-object load benches, and source-proof measurement rather than
  sampled C-level profiles.
- Current phase: `stacked`
- The stacked branch reproduced the clean validation shape without any new
  failures, which is the important result for this family: the reference-list
  helper specialization composes cleanly with the existing winner stack.
