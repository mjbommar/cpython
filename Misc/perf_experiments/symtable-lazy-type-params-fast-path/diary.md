        # symtable lazy type_params fast path

        Branch: `exp-symtable/lazy-type-params-mainline`
        Base commit: `5ac21d6bf53dda11ae6fdb2209dca725427b956a`
        Manifest: `Misc/perf_experiments/symtable-lazy-type-params-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split plus lazy allocation. symtable analysis currently allocates and copies type_params sets for every block even though PEP 695 generic type parameters are rare in normal source. Making the type_params set nullable and allocating/copying it only when a DEF_TYPE_PARAM symbol is actually encountered may remove one container from every analyze_block / analyze_child_block path without changing generic scoping semantics.

        ## Targets

        - Python/symtable.c:1374 symtable_analyze
- Python/symtable.c:1329 analyze_child_block
- Python/symtable.c:671 analyze_name

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - ranked deep-runtime / compile-pipeline choke point:
            - `Python/compile.c:_PyAST_Compile`
          - targeted source inspection:
            - `Python/symtable.c:symtable_analyze`
            - `Python/symtable.c:analyze_child_block`
            - `Python/symtable.c:analyze_name`
        - Usage scan:
          - archetype: `common-case split` plus `lazy allocation`
          - direct source read showed `type_params` is created in
            `symtable_analyze()` for every compilation and copied again in
            every `analyze_child_block()` call, even though generic type
            parameters are rare outside PEP 695 code
          - candidate shape:
            - make `type_params` nullable
            - allocate on first `DEF_TYPE_PARAM`
            - skip child-set copies when the incoming set is `NULL`
        - Initial benchmark corpus:
          - `benchmarks/bench_symtable_type_params.py`
          - `symtable.symtable()` cases:
            - `S1_module_assign`
            - `S2_nested_functions`
            - `S3_class_methods`
            - `S4_comprehensions`
            - `S5_generic_function`
            - `S6_generic_class`
        - Guardrails:
          - `guardrails/check_symtable_type_params_semantics.py`
          - covers:
            - nested free-variable lookup
            - generic function type parameter symbol
            - generic class type parameter symbol
            - `nonlocal T` rejection for type parameters

        ## Candidate Ledger

        ### E1

        Status: rejected at source proof.

        Thesis:

        - Make `type_params` nullable in the symtable analysis pipeline and
          allocate/copy it only when a block actually introduces
          `DEF_TYPE_PARAM`.

        Result:

        - Guardrail:
          - `symtable type_params semantics: ok`
        - Runtime / clean baseline:
          - `S1_module_assign`: `212,991,153.3 ns`
          - `S2_nested_functions`: `199,791,741.2 ns`
          - `S3_class_methods`: `210,721,450.6 ns`
          - `S4_comprehensions`: `175,351,150.5 ns`
          - `S5_generic_function`: `140,883,711.5 ns`
          - `S6_generic_class`: `178,001,872.3 ns`
        - First source proof pass:
          - `S1_module_assign`: `212,991,153.3 ns -> 206,579,817.5 ns` (`+3.10%`)
          - `S2_nested_functions`: `199,791,741.2 ns -> 194,228,711.3 ns` (`+2.86%`)
          - `S3_class_methods`: `210,721,450.6 ns -> 208,183,169.5 ns` (`+1.22%`)
          - `S4_comprehensions`: `175,351,150.5 ns -> 167,773,749.0 ns` (`+4.52%`)
          - `S5_generic_function`: `140,883,711.5 ns -> 137,742,177.3 ns` (`+2.28%`)
          - `S6_generic_class`: `178,001,872.3 ns -> 178,465,828.4 ns` (`-0.26%`)
          - geomean: `1.022763x` (`+2.28%`)
        - Implementation/debugging lesson:
          - the first nullable implementation crashed the bootstrap build via
            a `Py_DECREF(NULL)` success-path bug in `analyze_child_block()`
          - after fixing that and adding cleanup for lazily created local
            sets, the build and semantic guardrail were green
        - Reverted same-worktree baseline:
          - baseline drift geomean versus the first baseline:
            `1.029411x`
        - Averaged baseline versus candidate:
          - `S1_module_assign`: `+0.99%`
          - `S2_nested_functions`: `+1.74%`
          - `S3_class_methods`: `-0.75%`
          - `S4_comprehensions`: `+3.09%`
          - `S5_generic_function`: `+1.00%`
          - `S6_generic_class`: `-1.11%`
          - geomean: `1.008162x` (`+0.82%`)

        Decision:

        - Rejected before focused/full validation.
        - The shape looked initially promising, but the stricter same-worktree
          A/B check showed more baseline drift than believable retained win.
        - The generic cases were not catastrophic, but they also failed to
          justify carrying extra nullable-set complexity into review.

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
        - This is another reminder that “one container less per block” can
          sound structural and still be too small once build/layout drift is
          accounted for.
