        # compile ast structural fast path

        Branch: `exp-compile/ast-structural-mainline`
        Base commit: `0cdb89807fbb8afb2df333f8bc98eaef5babe3a6`
        Manifest: `Misc/perf_experiments/compile-ast-compile-structural-fast-path/experiment.json`

        ## Goal

        Control-flow lifting plus common-case split: the real remaining compile opportunity is likely below _PyAST_Compile() in compiler_mod() / optimize-and-assemble work, not another entry/setup tweak. First step is phase attribution to find a lower structural common path worth proving.

        ## Targets

        - Python/compile.c:1523 _PyAST_Compile
- Python/compile.c:1504 _PyCompile_OptimizeAndAssemble

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - `Misc/perf_experiments/reports/stacked-discovery-candidates-2026-04-24.md`
          - broader top-25 review still points at:
            - `Python/compile.c:1523 _PyAST_Compile`
        - Usage scan:
          - archetype: `control-flow lifting` plus `common-case split`
          - explicit exclusion:
            - do not retry the already-rejected lazy `c_stack` allocation
              tweak from `compile-lazy-compiler-stack-fast-path`
          - current thesis:
            - `_PyAST_Compile()` is still a high-value choke point, but the
              remaining win is likely lower in `compiler_mod()` /
              `_PyCompile_OptimizeAndAssemble()` / assembly work rather than in
              entry setup
          - next gate:
            - attribute compile time by phase before any prototype branch
            - only open code experiments if a lower structural phase shows
              meaningful headroom
- Initial benchmark corpus:
  - `benchmarks/bench_compile_phase_attribution.py`
  - results:
    - `benchmarks/results/runtime-phase-attribution.json`
  - source-proof harness:
    - `benchmarks/bench_compile_ast_structural.py`
    - helper module:
      - `helpers.py`
    - results:
      - `benchmarks/results/source-baseline-e2.json`
      - `benchmarks/results/source-candidate-e2.json`
      - `benchmarks/results/runtime-phase-attribution-candidate-e2.json`
- Guardrails:
  - `guardrails/check_compile_phase_attribution_semantics.py`
  - result:
    - `compile phase attribution semantics: ok`
  - `guardrails/check_compile_ast_structural_semantics.py`
  - result:
    - `compile ast structural semantics: ok`

        ## Candidate Ledger

        ### E1

        Status: completed attribution pass.

        Thesis:

        - first prove where compile time is actually going inside the C
          pipeline before choosing a structural fast path

        Result:

        - measurement-only instrumentation was added on the clean proof branch
          behind `PYTHON_COMPILE_PHASE_STATS`, restricted to
          `[perf-compile]...` filenames, and used only for this family's
          benchmark driver
        - focused attribution benchmark:
          - `benchmarks/bench_compile_phase_attribution.py`
          - `180` instrumented compiles per case
        - phase attribution summary:
          - `A1_module_assign` total `10,292.7 ns`
            - setup `22.08%`
            - symtable `18.18%`
            - codegen `18.70%`
            - optasm `47.55%`
            - inside optasm:
              - `code_unit` `43.32%`
              - `cfg_opt` `11.20%`
              - `cfg_to_instr` `9.91%`
              - `assemble` `17.38%`
          - `A2_module_many_assign` total `229,190.2 ns`
            - setup `25.69%`
            - symtable `23.10%`
            - codegen `37.36%`
            - optasm `32.67%`
            - inside optasm:
              - `code_unit` `32.22%`
              - `cfg_from_instr` `4.15%`
              - `cfg_opt` `5.04%`
              - `cfg_to_instr` `14.74%`
              - `assemble` `7.45%`
          - `A3_function_module` total `20,588.3 ns`
            - setup `28.51%`
            - symtable `23.81%`
            - codegen `46.93%`
            - optasm `18.52%`
          - `A4_class_module` total `37,287.1 ns`
            - setup `22.31%`
            - symtable `19.68%`
            - codegen `60.99%`
            - optasm `12.10%`
          - `A5_nested_functions` total `32,516.7 ns`
            - setup `24.93%`
            - symtable `22.43%`
            - codegen `59.72%`
            - optasm `10.72%`
          - `A6_list_comprehension` total `26,592.3 ns`
            - setup `22.33%`
            - symtable `19.43%`
            - codegen `16.48%`
            - optasm `55.22%`
            - inside optasm:
              - `code_unit` `53.10%`
              - `cfg_from_instr` `4.06%`
              - `cfg_opt` `14.01%`
              - `cfg_to_instr` `22.54%`
              - `assemble` `11.51%`
        - cross-case takeaway:
          - preprocess is small everywhere (`~1.9%` to `2.7%`)
          - setup is real but only about a quarter of total compile time
          - the real remaining compile split is:
            - `compiler_codegen()` for function/class/nested-heavy cases
            - `_PyCompile_OptimizeAndAssemble()` for flat-module and
              comprehension-heavy cases
          - inside `optimize_and_assemble_code_unit()`, the meaningful headroom
            is in the code-unit body, especially
            `_PyCfg_OptimizedCfgToInstructionSequence()` and assembly
          - `compute_code_flags()` and `_PyCodegen_AddReturnAtEnd()` are
            effectively noise (`<= 0.45%`)

Decision:

- Keep the family active, but explicitly stop considering setup /
  preprocess micro-tweaks for this line of work.
- For this compile-family branch, the next promising target is the
          lower `optimize_and_assemble_code_unit()` path, not another
          `_PyAST_Compile()` entry/setup change.
- The function/class/nested-heavy `compiler_codegen()` dominance is
  real, but that likely belongs in a separate future codegen family if
  we choose to chase it.

### E2

Status: accepted and stacked.

Thesis:

- Stay below `_PyAST_Compile()` setup and target the optasm-heavy path
  directly: when `_PyCfg_ToInstructionSequence()` receives an empty
  instruction sequence, pre-count instructions and labels, allocate once,
  and fill the destination arrays directly instead of growing them through
  `_PyInstructionSequence_UseLabel()` / `_PyInstructionSequence_Addop()`
  in the inner loop.

Result:

- Clean source patch on `exp-compile/ast-structural-mainline`:
  - `Python/flowgraph.c:_PyCfg_ToInstructionSequence()`
  - add an empty-sequence specialization that:
    - counts labels and total instructions first
    - allocates `seq->s_instrs` and `seq->s_labelmap` once
    - fills instructions directly
    - then applies the label map once at the end
  - fallback path keeps the old generic growth logic untouched
- Phase-attribution candidate check against `runtime-phase-attribution.json`:
  - `A1_module_assign`: `+7.93%`
  - `A2_module_many_assign`: `+7.72%`
  - `A3_function_module`: `-10.45%`
  - `A4_class_module`: `+5.34%`
  - `A5_nested_functions`: `+9.37%`
  - `A6_list_comprehension`: `+23.90%`
  - geomean: about `+6.82%`
- Clean same-worktree AST-only source proof:
  - baseline artifact:
    - `benchmarks/results/source-baseline-e2.json`
  - candidate artifact:
    - `benchmarks/results/source-candidate-e2.json`
  - details:
    - `C1_module_assign`: `+5.61%`
    - `C2_module_many_assign`: `+2.44%`
    - `C3_function_module`: `+4.73%`
    - `C4_class_module`: `+5.63%`
    - `C5_nested_functions`: `+2.19%`
    - `C6_list_comprehension`: `+3.08%`
  - geomean: about `+3.94%`
- Guardrail:
  - phase-attribution semantics: passed
  - AST structural semantics: passed

Decision:

- Accepted on the clean branch and promoted to the stacked branch. The
  attribution-only comparison had one concerning regression on
  `A3_function_module`, but the same-worktree AST-only source proof came
  back broadly positive and the candidate then cleared focused and full
  validation on both the clean and stacked branches.

## Validation

- Guardrails:
  - phase-attribution guardrail: passed
  - clean source AST structural guardrail: passed
  - stacked AST structural guardrail: passed
- Focused tests:
  - clean branch `exp-compile/ast-structural-mainline`:
    - `test_compile test_ast`: passed
    - `test_symtable test_dis`: passed
  - stacked branch `exp-combined-winners-local`:
    - `test_compile test_ast`: passed
    - `test_symtable test_dis`: passed
- Full suite:
  - clean branch:
    - `49,882` run
    - `2,623` skipped
    - `SUCCESS` in `4 min 20 sec`
  - stacked branch:
    - `49,892` run
    - `2,620` skipped
    - `SUCCESS` in `4 min 18 sec`
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: accepted and stacked
- Accepted commit: `2d319755662`
- Stacked winner commit: `3978a15ff66`

## Notes

- Keep rejected ideas here too so the branch remains useful research.
- This family exists specifically to avoid reopening entry/setup
  compiler tweaks that already failed.
- The measurement-only proof patch lives only on the clean experiment
  worktree branch and has not been promoted anywhere.
- Current phase: `stacked`
