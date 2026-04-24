        # tokenizer file line length fast path

        Branch: `exp-tokenizer/file-line-length-mainline`
        Base commit: `a9895a588d4aea081e8f2903b0c59ee08d9cf5a7`
        Manifest: `Misc/perf_experiments/tokenizer-file-line-length-fast-path/experiment.json`

        ## Goal

        Archetype: control-flow lifting plus common-case data reuse. The raw file tokenizer path already knows exact line bounds via tok->inp, but tok_underflow_file() rescans the same bytes with strlen() for coding-cookie checks and UTF-8 or codec validation. Reusing pointer-difference lengths may remove redundant per-line scans on source-file compilation without changing tokenizer semantics.

        ## Targets

        - Parser/tokenizer/file_tokenizer.c:tok_underflow_file
- Parser/tokenizer/file_tokenizer.c:_PyTokenizer_FromFile

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

## Input Evidence

- Profiles:
- Profiles:
  - ranked from the current deep-runtime review list:
    - `Parser/tokenizer/file_tokenizer.c:373 _PyTokenizer_FromFile`
    - adjacent file-source parser entry:
      `Parser/pegen.c:988 _PyPegen_run_parser_from_file_pointer`
- Usage scan:
- Usage scan:
  - caller path inspection:
    - `Parser/peg_api.c:_PyParser_ASTFromFile()` calls
      `_PyPegen_run_parser_from_file_pointer()`
    - `_PyPegen_run_parser_from_file_pointer()` creates the tokenizer with
      `_PyTokenizer_FromFile()`
    - the real recurring file-source work is then in
      `tok_underflow_file()`, not the tiny `_PyTokenizer_FromFile()` wrapper
  - real remaining hypothesis after the rejected string-tokenizer family:
    - string-source newline normalization was too weak (`+1.08%` geomean)
    - file-source tokenization still does extra rescans
  - concrete source observation:
    - `tok_underflow_file()` already knows line bounds through `tok->inp`
    - it still calls `strlen(tok->cur)` for coding-cookie inspection
    - it later calls `strlen(line)` again for UTF-8 or codec validation
- Initial benchmark corpus:
- Initial benchmark corpus:
  - `benchmarks/bench_tokenizer_file_lines.py`
  - cases:
    - `F1_short_comments`
    - `F2_long_comments`
    - `F3_utf8_cookie_long_comments`
    - `F4_latin1_cookie_long_comments`
    - `F5_mixed_module`
- Guardrails:
- Guardrails:
  - `guardrails/check_tokenizer_file_line_semantics.py`
  - covers:
    - UTF-8 cookie execution
    - latin-1 cookie execution
    - missing trailing newline
    - syntax error line reporting

        ## Candidate Ledger

        ### E1

        Status: pending.

Thesis:

- Reuse `tok->inp - tok->cur` / `tok->inp - line` lengths in
  `tok_underflow_file()` instead of rescanning the same bytes with `strlen()`
  before coding-cookie and decode validation.

Result:

- clean same-worktree source proof on
  `exp-tokenizer/file-line-length-mainline`
- result artifacts:
  - `benchmarks/results/runtime-baseline.json`
  - `benchmarks/results/source-baseline.json`
  - `benchmarks/results/source-candidate.json`
- clean source A/B:
  - `F1_short_comments`: `-0.40%`
  - `F2_long_comments`: `-1.88%`
  - `F3_utf8_cookie_long_comments`: `-0.33%`
  - `F4_latin1_cookie_long_comments`: `-0.97%`
  - `F5_mixed_module`: `+1.09%`
  - geomean: `0.994991x` (`-0.50%`)
- clean guardrail:
  - `check_tokenizer_file_line_semantics.py`: `ok`

Decision:

- Reject.
- The local `strlen()` reuse is semantics-safe but does not survive the
  same-worktree source gate. The file-source tokenizer still needs a stronger
  shape than this redundant-length cleanup.

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
- The important triage lesson is that `_PyTokenizer_FromFile()` itself was too
  thin to be the real target. The deeper `tok_underflow_file()` path was the
  correct review boundary, but even there this specific pointer-length reuse
  was too weak.
- The benchmark harness intentionally used whole-file subprocess execution with
  `-S -B` and large comment-heavy scripts so the measurements hit the raw
  file-source tokenizer path rather than the already-rejected string-source
  tokenizer path.
