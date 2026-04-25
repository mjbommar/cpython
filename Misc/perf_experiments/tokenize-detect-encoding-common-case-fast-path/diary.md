        # tokenize detect encoding common case fast path

        Branch: `exp-tokenize/detect-encoding-mainline`
        Base commit: `faa7d29705c03f8ab5141a015128de52fe932f61`
        Manifest: `Misc/perf_experiments/tokenize-detect-encoding-common-case-fast-path/experiment.json`

        ## Goal

        Archetype: `common-case split`.
        `tokenize.detect_encoding()` pays regex and blank-line checks even when
        the first line is already a non-comment, nonblank UTF-8 line with no
        BOM or coding cookie, which is the dominant stdlib shape.

        ## Targets

        - Lib/tokenize.py:358 detect_encoding

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - fresh stacked discovery report:
            - `Misc/perf_experiments/reports/stacked-discovery-candidates-2026-04-25.md`
          - relevant fresh group signal:
            - `Lib/tokenize.py` about `138` leaf samples (`0.53%`)
        - Usage scan:
          - stdlib AST call census:
            - `tokenize.detect_encoding`: `36`
            - `tokenize.open`: `14`
          - high-value stdlib callers:
            - `importlib._bootstrap_external.decode_source`
            - `linecache`
            - `pydoc`
            - `trace`
            - `pdb`
            - `idlelib`
          - first-line shape scan across `Lib/**/*.py`:
            - nonblank noncomment first line: `1587 / 1987` (`79.87%`)
            - comment or shebang first line: `361 / 1987` (`18.17%`)
            - leading blank first line: `13 / 1987` (`0.65%`)
            - empty file: `26 / 1987` (`1.31%`)
            - BOM present: `1 / 1987` (`0.05%`)
        - Initial benchmark corpus:
          - `benchmarks/bench_tokenize_detect_encoding.py`
          - cases:
            - `T1_detect_ascii_docstring`
            - `T2_detect_utf8_docstring`
            - `T3_detect_comment_cookie`
            - `T4_detect_shebang_cookie`
            - `T5_detect_bom_default`
            - `T6_open_default`
            - `T7_open_cookie`
            - `T8_decode_source_default`
        - Guardrails:
          - `guardrails/check_tokenize_detect_encoding_semantics.py`
          - target result:
            - `tokenize detect_encoding semantics: ok`

        ## Candidate Ledger

        ### E1

        Status: rejected at runtime proof.

        Thesis:

        - split out the dominant no-comment, no-cookie path in
          `detect_encoding()`: after BOM handling, if the first line starts
          with real source text rather than `#` or whitespace, validate it as
          UTF-8 and return immediately before any regex or second-line logic

        Result:

        - guardrail:
          - `check_tokenize_detect_encoding_semantics.py`: passed
        - runtime proof, initial helper form:
          - `T1_detect_ascii_docstring`: `-0.61%`
          - `T2_detect_utf8_docstring`: `-3.18%`
          - `T3_detect_comment_cookie`: `-18.96%`
          - `T4_detect_shebang_cookie`: `-12.96%`
          - `T5_detect_bom_default`: `+1.50%`
          - `T6_open_default`: `+2.16%`
          - `T7_open_cookie`: `-3.24%`
          - `T8_decode_source_default`: `+5.83%`
          - geomean: about `-4.01%`
        - runtime proof, tightened helper closer to source shape:
          - `T1_detect_ascii_docstring`: `+1.26%`
          - `T2_detect_utf8_docstring`: `+2.49%`
          - `T3_detect_comment_cookie`: `-18.92%`
          - `T4_detect_shebang_cookie`: `-14.98%`
          - `T5_detect_bom_default`: `+4.01%`
          - `T6_open_default`: `+5.92%`
          - `T7_open_cookie`: `-3.05%`
          - `T8_decode_source_default`: `+7.91%`
          - geomean: about `-2.38%`

        Decision:

        - Rejected before any clean source branch. The intended common path is
          real, but the comment/cookie control shapes regress hard enough that
          the family remains net negative even after tightening the runtime
          helper to resemble a real source patch more closely.

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
