        # pegen file main module static string fast path

        Branch: `exp-pegen/file-main-module-mainline`
        Base commit: `faedd2dedab033a10ebded599005301eb30ba45c`
        Manifest: `Misc/perf_experiments/pegen-file-main-module-static-string-fast-path/experiment.json`

        ## Goal

        Archetype: precomputed immutable state. _PyPegen_run_parser_from_file_pointer() allocates a fresh PyUnicode '__main__' on every file parse even though the value is static and already available as a global identifier object. Reusing the immortal static '__main__' string with Py_NewRef() may shave file-source parse setup cost without changing warning or error semantics.

        ## Targets

        - Parser/pegen.c:988 _PyPegen_run_parser_from_file_pointer
- Parser/pegen.c:1011 tok->module = PyUnicode_FromString("__main__")

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

## Input Evidence

- Profiles:
- Profiles:
  - ranked unresolved deep-runtime file-source path:
    - `Parser/pegen.c:988 _PyPegen_run_parser_from_file_pointer`
    - adjacent file tokenizer setup already reviewed separately
- Usage scan:
- Usage scan:
  - direct source inspection:
    - `_PyPegen_run_parser_from_file_pointer()` still does
      `PyUnicode_FromString("__main__")`
    - `tok->module` is only used on warning/error reporting paths below the
      tokenizer helpers
    - a static immortal identifier object for `__main__` already exists as
      `&_Py_ID(__main__)`
  - this makes the candidate a narrow immutable-state reuse, not a parser
    algorithm rewrite
- Initial benchmark corpus:
- Initial benchmark corpus:
  - `benchmarks/bench_pegen_file_main_module.py`
  - file-source cases:
    - `F1_short_comments`
    - `F2_long_comments`
    - `F3_utf8_cookie_long_comments`
    - `F4_latin1_cookie_long_comments`
    - `F5_mixed_module`
- Guardrails:
- Guardrails:
  - `guardrails/check_pegen_file_main_module_semantics.py`
  - covers:
    - UTF-8 cookie execution
    - latin-1 cookie execution
    - missing trailing newline
    - syntax error line reporting
    - invalid escape warning path

        ## Candidate Ledger

        ### E1

        Status: pending.

Thesis:

- Replace the per-parse `PyUnicode_FromString("__main__")` allocation in
  `_PyPegen_run_parser_from_file_pointer()` with `Py_NewRef(&_Py_ID(__main__))`.

Result:

- clean same-worktree source proof on
  `exp-pegen/file-main-module-mainline`
- result artifacts:
  - `benchmarks/results/source-baseline.json`
  - `benchmarks/results/source-candidate.json`
- clean source A/B:
  - `F1_short_comments`: `-6.00%`
  - `F2_long_comments`: `-0.67%`
  - `F3_utf8_cookie_long_comments`: `+0.05%`
  - `F4_latin1_cookie_long_comments`: `+1.01%`
  - `F5_mixed_module`: `-0.22%`
  - geomean: `0.988020x` (`-1.20%`)
- clean guardrail:
  - `check_pegen_file_main_module_semantics.py`: `ok`

Decision:

- Reject.
- The static `__main__` reuse is reviewable and semantics-safe, but it does not
  survive same-worktree source proof on real file-source parsing.

## Validation

- Focused tests:
- Focused tests:
  - not run
- Full suite:
- Full suite:
  - not run
- Ecosystem / third-party:
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision:
- Decision: rejected
- Accepted commit:
- Stacked winner commit:

## Notes

- Keep rejected ideas here too so the branch remains useful research.
- This is another example of a setup-level deep-runtime idea that looked
  cleaner than the previous tokenizer family but still failed the local source
  gate. The file-source parser path likely needs a more structural win than
  one small allocation removal.
