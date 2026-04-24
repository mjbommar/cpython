        # vectorcall noargs fast path

        Branch: `exp-call/vector-noargs-mainline`
        Base commit: `f1f80a20bbee28c77732c717631c01e2caf700bc`
        Manifest: `Misc/perf_experiments/vectorcall-noargs-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split. _PyFunction_Vectorcall() and _PyEval_Vector() currently pay small but unconditional setup costs even for the common zero-argument, no-keyword Python-function call path. A dedicated noargs fast path may remove stack-copy and branch overhead from the hottest pure-Python call boundary without changing frame semantics.

        ## Targets

        - Objects/call.c:402 _PyFunction_Vectorcall
- Python/ceval.c:2082 _PyEval_Vector

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - ranked deep-runtime choke point:
            - `Objects/call.c:_PyFunction_Vectorcall`
            - `Python/ceval.c:_PyEval_Vector`
            - `Python/ceval.c:initialize_locals`
        - Usage scan:
          - direct source inspection:
            - `_PyFunction_Vectorcall()` is a thin branch over `_PyEval_Vector()`
            - `_PyEval_Vector()` is already fairly lean for `argcount == 0`
            - the first non-trivial common-case split sits in
              `initialize_locals()`, where true noarg functions still walk the
              generic flag/default/keyword setup logic before returning
          - candidate shape:
            - early-return from `initialize_locals()` when:
              - `argcount == 0`
              - `kwnames == NULL`
              - `co_argcount == 0`
              - `co_kwonlyargcount == 0`
              - no `*args` / `**kwargs`
        - Initial benchmark corpus:
          - `benchmarks/bench_vectorcall_noargs.py`
          - cases:
            - `V1_plain_noargs`
            - `V2_bound_method_noargs`
            - `V3_closure_noargs`
            - `V4_defaults_called_noargs`
            - `V5_onearg_control`
        - Guardrails:
          - `guardrails/check_vectorcall_noargs_semantics.py`
          - covers:
            - plain noarg function
            - closure noarg function
            - bound noarg method
            - defaulted function called with no args
            - required kw-only failure path

        ## Candidate Ledger

        ### E1

        Status: rejected at source proof.

        Thesis:

        - Add an `initialize_locals()` early return for the exact true-noarg
          function shape instead of trying to optimize the thinner
          `_PyFunction_Vectorcall()` wrapper itself.

        Result:

        - Guardrail:
          - `vectorcall noargs semantics: ok`
        - Runtime baseline:
          - `V1_plain_noargs`: `68,901,502.0 ns`
          - `V2_bound_method_noargs`: `66,038,499.6 ns`
          - `V3_closure_noargs`: `56,452,772.7 ns`
          - `V4_defaults_called_noargs`: `67,515,452.4 ns`
          - `V5_onearg_control`: `75,577,533.5 ns`
        - Source proof pass A:
          - `V1_plain_noargs`: `69,647,206.7 ns -> 68,879,815.9 ns` (`+1.11%`)
          - `V2_bound_method_noargs`: `65,846,866.7 ns -> 64,916,979.9 ns` (`+1.43%`)
          - `V3_closure_noargs`: `58,404,768.4 ns -> 55,989,658.5 ns` (`+4.31%`)
          - `V4_defaults_called_noargs`: `67,202,854.5 ns -> 66,658,256.6 ns` (`+0.82%`)
          - `V5_onearg_control`: `77,763,200.5 ns -> 75,100,007.7 ns` (`+3.55%`)
          - geomean: `1.022349x` (`+2.23%`)
        - Source proof pass B, reverted baseline:
          - baseline drift geomean versus pass A baseline: `1.017662x`
        - Averaged baseline versus candidate:
          - `V1_plain_noargs`: `+0.24%`
          - `V2_bound_method_noargs`: `+1.16%`
          - `V3_closure_noargs`: `+2.84%`
          - `V4_defaults_called_noargs`: `+0.24%`
          - `V5_onearg_control`: `+2.28%`
          - geomean: `1.013487x` (`+1.35%`)

        Decision:

        - Rejected before focused/full validation.
        - The first-pass result looked mildly positive, but the reversion check
          showed enough baseline drift that the supposed win collapsed below the
          acceptance bar.
        - The control case (`V5_onearg_control`) moved almost as much as the
          targeted noarg cases, which points to code-layout noise rather than a
          clean noarg-path improvement.

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
        - The call boundary remains interesting, but this exact common-case
          split is too close to the noise floor. Any reopened call-spine work
          should target a more structural frame-setup cost, not another tiny
          branch elision inside `initialize_locals()`.
