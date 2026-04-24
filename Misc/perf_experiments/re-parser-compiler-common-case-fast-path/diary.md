# re parser compiler common-case fast path

Branch: `exp-re/parser-compiler-mainline`
Base commit: `ad7d3616c6cc21c5ec032a726e4c5e819628aa6e`
Manifest: `Misc/perf_experiments/re-parser-compiler-common-case-fast-path/experiment.json`

## Goal

Fresh stacked-branch discovery on a curated broad stdlib slice still showed a
real pure-Python regex compile cluster: `re.__init__._compile`,
`re._compiler.compile`, `re._parser.parse`, `_parse_sub`, and `_parse`. The
right archetype here was `common-case split` plus `control-flow lifting`, but
inside the parser/compiler pipeline rather than the public cache wrapper.

## Targets

- `Lib/re/_compiler.py:757 compile`
- `Lib/re/_parser.py:962 parse`
- `Lib/re/_parser.py:452 _parse_sub`
- `Lib/re/_parser.py:511 _parse`

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
  - fresh curated discovery profile on:
    `test_dataclasses test_dbm_sqlite3 test_tempfile test_traceback
    test_argparse test_shutil test_pathlib test_re test_pickle test_random`
  - strongest relevant cumulative leaves:
    - `Lib/re/__init__.py:_compile`: about `1.527s`
    - `Lib/re/_compiler.py:compile`: about `1.255s`
    - `Lib/re/_parser.py:parse`: about `0.723s`
    - `Lib/re/_parser.py:_parse_sub`: about `0.669s`
    - `Lib/re/_parser.py:_parse`: about `0.609s`
- Usage scan:
  - direct `_compiler.compile()` attribution on representative shapes showed
    `SubPattern.__getitem__`, `SubPattern.__delitem__`, and `_parse_sub`
    dominating branch-heavy patterns more than `groupindex` bookkeeping did
  - the public cache wrapper was not the main leverage point for this family
- Initial benchmark corpus:
  - `benchmarks/bench_re_parser_compiler.py`
  - key cases:
    - `R1_literal`
    - `R2_literal_bytes`
    - `R3_captures`
    - `R4_named_groups`
    - `R5_charset`
    - `R6_branch_prefix`
    - `R7_quantified`
    - `R8_lookahead`
    - `R9_ignorecase`
    - `R10_alternation`
    - `R11_branch_repeat`
    - `R12_charset_branch`
    - `R10_stdlib_compile_corpus`
    - `R11_re_tests_compile_corpus`
  - result artifacts:
    - `benchmarks/results/e1-runtime.json`
    - `benchmarks/results/e1-candidate.json`
    - `benchmarks/results/e2-runtime.json`
    - `benchmarks/results/e2-candidate.json`
    - `benchmarks/results/e3-runtime.json`
    - `benchmarks/results/e3-candidate.json`
    - `benchmarks/results/e3-source-base.json`
    - `benchmarks/results/e3-source-candidate.json`
- Guardrails:
  - `guardrails/check_re_parser_compiler_semantics.py`
  - result: `re parser/compiler guardrails: ok`

## Candidate Ledger

### E1

Status: rejected.

Thesis:

- Fast-path `_compiler.compile()` when `p.state.groupdict` is empty so the
  common unnamed-group case skips dict construction work.

Result:

- Runtime proof only:
  - geomean: `1.027145x`
  - strongest cases:
    - `R1_literal`: `+8.85%`
    - `R2_literal_bytes`: `+7.38%`
    - `R10_stdlib_compile_corpus`: `+1.81%`
    - `R11_re_tests_compile_corpus`: `+1.14%`
- Source proof on the clean worktree:
  - geomean: `1.003390x`

Decision:

- Rejected. This looked real in monkeypatch form but collapsed after the actual
  source substitution. The source gate prevented promoting a thin illusion.

### E2

Status: rejected.

Thesis:

- Lazily initialize `State.groupdict` so ordinary unnamed-group patterns avoid
  even creating the dict until a named group is encountered.

Result:

- Runtime proof only:
  - geomean: `1.006403x`

Decision:

- Rejected. Too weak even before a source branch.

### E3

Status: accepted and stacked.

Thesis:

- In `_parse_sub()`, stop paying `SubPattern.__getitem__`,
  `SubPattern.__len__`, and `SubPattern.__delitem__` overhead in the branch
  rewrite logic. Operate on `item.data` directly for the common branch-prefix
  and charset rewrite path while keeping the higher-level structure unchanged.

Result:

- Runtime proof on the official harness:
  - geomean: `1.019845x`
  - strongest cases:
    - `R6_branch_prefix`: `+10.04%`
    - `R11_branch_repeat`: `+5.24%`
    - `R12_charset_branch`: `+5.09%`
    - `R11_re_tests_compile_corpus`: `+5.44%`
    - `R10_stdlib_compile_corpus`: `+0.48%`
- Clean source proof:
  - geomean: `1.024957x`
  - strongest cases:
    - `R6_branch_prefix`: `+9.67%`
    - `R11_branch_repeat`: `+6.24%`
    - `R12_charset_branch`: `+4.15%`
    - `R11_re_tests_compile_corpus`: `+2.21%`
    - `R10_stdlib_compile_corpus`: `+0.70%`

Decision:

- Accepted. This was the first candidate that stayed positive through runtime
  proof, source proof, focused tests, and both clean and stacked full-suite
  validation.

## Validation

- Focused tests:
  - guardrail:
    - `./python Misc/perf_experiments/re-parser-compiler-common-case-fast-path/guardrails/check_re_parser_compiler_semantics.py`
    - result: passed (`re parser/compiler guardrails: ok`)
  - clean branch:
    - `./python -m test -j4 test_re`
      - result: passed
    - `./python -m test -j4 test_argparse test_glob test_pathlib`
      - result: passed
    - `./python -m test -j4 test_email test_traceback test_pydoc`
      - result: passed
  - stacked branch:
    - `/home/mjbommar/projects/personal/cpython-combined-winners/python /home/mjbommar/projects/personal/cpython/Misc/perf_experiments/re-parser-compiler-common-case-fast-path/guardrails/check_re_parser_compiler_semantics.py`
      - result: passed (`re parser/compiler guardrails: ok`)
    - `./python -m test -j4 test_re`
      - result: passed
    - `./python -m test -j4 test_argparse test_glob test_pathlib`
      - result: passed
    - `./python -m test -j4 test_email test_traceback test_pydoc`
      - result: passed
- Full suite:
  - clean branch:
    - `./python -m test -j8`
    - result: passed
    - summary: `49,882` run, `2,623` skipped, `476 tests OK`, `SUCCESS`, `4 min 19 sec`
  - stacked branch:
    - `./python -m test -j8`
    - result: passed
    - summary: `49,892` run, `2,621` skipped, `476 tests OK`, `SUCCESS`, `4 min 18 sec`
- Ecosystem / third-party:
  - none

## Acceptance Decision

- Decision: accepted and stacked
- Accepted commit: `01f9cfcb833`
- Stacked winner commit: `5850e18e621`

## Notes

- The winning shape was not named-group bookkeeping. The better signal came
  only after looking at direct parser/compiler attribution instead of the broad
  wrapper cluster.
- This family is a good example of why the process keeps rejected candidates in
  the diary. Both E1 and E2 looked plausible from source reading alone, but
  only E3 survived the full funnel.
