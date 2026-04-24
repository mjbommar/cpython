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

Status: pending.

Thesis:

Pending code inspection in `Python/marshal.c`.

Result:

Not yet attempted.

Decision:

Not yet attempted.

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

- Decision: pending
- Accepted commit:
- Stacked winner commit:

## Notes

- Current phase: `benchmarks`
- The next gate is candidate enumeration inside `marshal.c`, likely around
  code-object-heavy read paths rather than the tiny `PyMarshal_ReadObjectFromString()`
  wrapper itself.
