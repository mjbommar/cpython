        # pegen string entry common-case fast path

        Branch: `exp-pegen/string-entry-mainline`
        Base commit: `386bd50f59126b6c0237b9399f6cd9c6792a06e3`
        Manifest: `Misc/perf_experiments/pegen-string-entry-common-case-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split plus control-flow lifting. _PyPegen_run_parser_from_string() is the string-source parser entry used by compile(), eval(), exec(), ast.parse(), and symtable. The dominant path appears to be module==NULL with no parser-affecting flags, where tokenizer choice, parser flags, and feature-version selection are all fixed. A split for that exact shape may reduce front-end setup cost without changing parser semantics.

        ## Targets

        - Parser/pegen.c:_PyPegen_run_parser_from_string
- Parser/peg_api.c:_PyParser_ASTFromString

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - ranked from the current deep-runtime top-25 review list:
            `Parser/pegen.c:1041 _PyPegen_run_parser_from_string`
        - Usage scan:
          - `_PyPegen_run_parser_from_string()` is reached via
            `_PyParser_ASTFromString()` from:
            - `_Py_CompileStringObjectWithModule()`
            - `PyRun_StringFlags()`
            - builtin `compile()`
            - `ast.parse()`
            - `symtable.symtable()`
          - likely common case:
            - string input
            - `module == NULL`
            - no parser-affecting flags
          - special control shapes to preserve:
            - `PyCF_ONLY_AST`
            - `PyCF_IGNORE_COOKIE`
            - type comments
            - incomplete input
        - Initial benchmark corpus:
          - `P1_compile_exec_small`
          - `P2_compile_eval_small`
          - `P3_compile_function_module`
          - `P4_ast_parse_function_module`
          - `P5_ast_parse_type_comments`
          - `P6_symtable_function_module`
          - `P7_codeop_incomplete`
          - baseline means:
            - `P1`: `17701.0 ns`
            - `P2`: `10650.2 ns`
            - `P3`: `60274.3 ns`
            - `P4`: `42350.4 ns`
            - `P5`: `14235.8 ns`
            - `P6`: `41862.4 ns`
            - `P7`: `28523.1 ns`
        - Guardrails:
          - `check_pegen_string_entry_semantics.py`
          - passed

        ## Candidate Ledger

        ### E1

        Status: rejected.

        Thesis:

        - Split `_PyPegen_run_parser_from_string()` on the exact common case
          `module == NULL` and `flags == NULL || flags->cf_flags == 0`.
        - In that branch:
          - always call `_PyTokenizer_FromString(...)`
          - hardcode `parser_flags = 0`
          - hardcode `feature_version = PY_MINOR_VERSION`
        - Keep the original generic path for cookie-ignore, AST-only,
          type-comments, incomplete-input, and explicit module cases.

        Result:

        - clean worktree:
          `/home/mjbommar/projects/personal/cpython-pegen-string-entry-mainline`
        - candidate guardrail: passed
        - same-worktree source A/B:
          - `P1_compile_exec_small`: `-0.04%`
          - `P2_compile_eval_small`: `-0.61%`
          - `P3_compile_function_module`: `+1.32%`
          - `P4_ast_parse_function_module`: `-0.71%`
          - `P5_ast_parse_type_comments`: `+1.95%`
          - `P6_symtable_function_module`: `-0.09%`
          - `P7_codeop_incomplete`: `+0.85%`
          - geomean: `+0.38%`

        Decision:

        - Reject.
        - The setup split is too small. The measured gain does not justify
          focused/full validation or a stacked promotion attempt.

        ## Validation

        - Focused tests:
        - Full suite:
        - Ecosystem / third-party:

        ## Acceptance Decision

        - Decision: rejected
        - Accepted commit:
        - Stacked winner commit:

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Current phase: `rejected`
        - `_PyAST_Compile()` still looks like the thinner wrapper trap of the
          two deep-runtime candidates. The stronger next parser/compiler target
          is likely lower than `_PyPegen_run_parser_from_string()`, not above
          it.
