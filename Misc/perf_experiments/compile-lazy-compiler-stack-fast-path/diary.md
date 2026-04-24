        # compile lazy compiler stack fast path

        Branch: `exp-compile/lazy-stack-mainline`
        Base commit: `c6ef4d3e1091032c5347f1adbd94fe9bc4b0b6db`
        Manifest: `Misc/perf_experiments/compile-lazy-compiler-stack-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split plus lazy allocation. _PyAST_Compile() currently allocates c_stack as an empty list for every compile even though many AST compiles never enter nested scopes. Lazily allocating c_stack on first nested scope push may remove one guaranteed allocation from the hot compile setup path without changing qualname or nested-scope semantics.

        ## Targets

        - Python/compile.c:112 compiler_setup
- Python/compile.c:595 _PyCompile_EnterScope
- Python/compile.c:733 _PyCompile_ExitScope

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

## Input Evidence

- Profiles:
- Profiles:
  - ranked deep-runtime choke point:
    - `Python/compile.c:1523 _PyAST_Compile`
- Usage scan:
- Usage scan:
  - direct source inspection:
    - `compiler_setup()` always allocates `c_stack = PyList_New(0)`
    - nested scopes only push onto `c_stack` when `c->u` already exists and a
      child scope is entered
    - simple AST compiles with no nested function/class/comprehension traffic
      never need to append anything to `c_stack`
  - candidate shape:
    - lazily allocate `c_stack` on first nested scope push
- Initial benchmark corpus:
- Initial benchmark corpus:
  - `benchmarks/bench_compile_lazy_stack.py`
  - AST-input cases:
    - `C1_module_assign`
    - `C2_module_many_assign`
    - `C3_function_module`
    - `C4_class_module`
    - `C5_nested_functions`
    - `C6_list_comprehension`
- Guardrails:
- Guardrails:
  - `guardrails/check_compile_lazy_stack_semantics.py`
  - covers:
    - plain module execution
    - nested function qualnames and closure behavior
    - class method qualnames
    - comprehension execution

        ## Candidate Ledger

        ### E1

        Status: rejected at source proof.

Thesis:

- Make `c_stack` lazy so `_PyAST_Compile()` does not pay for an empty list
  allocation until a nested scope is actually pushed.

        Result:

        - Guardrail:
          - `./python .../guardrails/check_compile_lazy_stack_semantics.py`
          - result: `compile lazy stack semantics: ok`
        - Baseline:
          - `C1_module_assign`: `39,740,507.3 ns`
          - `C2_module_many_assign`: `489,605,692.7 ns`
          - `C3_function_module`: `44,746,707.3 ns`
          - `C4_class_module`: `38,509,924.0 ns`
          - `C5_nested_functions`: `45,202,109.7 ns`
          - `C6_list_comprehension`: `52,276,190.7 ns`
        - Source proof:
          - `C1_module_assign`: `39,740,507.3 ns -> 39,605,777.6 ns` (`+0.34%`)
          - `C2_module_many_assign`: `489,605,692.7 ns -> 487,336,741.6 ns` (`+0.47%`)
          - `C3_function_module`: `44,746,707.3 ns -> 43,208,964.0 ns` (`+3.56%`)
          - `C4_class_module`: `38,509,924.0 ns -> 38,500,294.1 ns` (`+0.03%`)
          - `C5_nested_functions`: `45,202,109.7 ns -> 45,198,660.7 ns` (`+0.01%`)
          - `C6_list_comprehension`: `52,276,190.7 ns -> 52,126,374.7 ns` (`+0.29%`)
          - geomean: `1.007731x` (`+0.77%`)

        Decision:

        - Rejected before focused/full validation.
        - The guaranteed empty-list allocation in `compiler_setup()` is real, but
          removing it is not a meaningful compile-pipeline win on this focused
          AST corpus.
        - The only noticeable local movement was `C3_function_module`, and that
          single-case gain was not enough to justify taking a deep compiler
          lifetime change further.

        ## Validation

        - Focused tests: not run
        - Full suite: not run
        - Ecosystem / third-party: not run

        ## Acceptance Decision

        - Decision: rejected
        - Accepted commit:
        - Stacked winner commit:

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Compiler setup looks like another case where a thin setup-layer
          allocation tweak is too small by itself. The next better compiler
          target is likely a lower, more structural `_PyAST_Compile()` or codegen
          shape rather than another entry/setup micro-guard.
