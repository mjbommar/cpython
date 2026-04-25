        # Unicode strip whitespace 1-byte fast paths

        Branch: `exp-unicode/strip-whitespace-1byte-mainline`
        Base commit: `ad7d3616c6cc21c5ec032a726e4c5e819628aa6e`
        Manifest: `Misc/perf_experiments/unicode-strip-whitespace-1-byte-fast-paths/experiment.json`

        ## Goal

        Whitespace strip/lstrip/rstrip spend measurable runtime in parser and email-style text workloads; tighter 1-byte trimming loops can reduce total runtime while preserving full Unicode whitespace semantics.

        ## Targets

        - Objects/unicodeobject.c:12359 do_strip

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Archetype: common-character specialization / input-shape snapshot (`perf_patterns.md` section 1.3a). This is the StringZilla trimming pattern narrowed to CPython's existing ASCII whitespace strip loop.
        - Profiles: `./python -m cProfile -o /tmp/isspace_test_email.prof -m test test_email` showed string trimming as a larger hotspot than `str.isspace`: `strip` about `0.044s`, `lstrip` about `0.041s`, and `rstrip` about `0.031s` self time. A candidate profile sample kept the same shape: `strip` `0.044847s`, `lstrip` `0.043067s`, `rstrip` `0.032010s`, `isspace` `0.000960s`.
        - Usage scan: trimming is common in `email`, `textwrap`, parser/tooling, and line-oriented stdlib code. The focused harness covers direct `strip`/`lstrip`/`rstrip` cases plus email-line and `textwrap.dedent`-shaped workloads.
        - Initial benchmark corpus: `bench_strip.py` measures space-padded, tab-space-padded, no-pad, Latin-1, BMP, email-line trim, and `textwrap.dedent` cases.
        - Guardrails: preserve full `_Py_ascii_whitespace` behavior and leave Latin-1/BMP Unicode whitespace semantics on the existing paths.

        ## Candidate Ledger

        ### E1

        Status: rejected.

        Thesis:

        - Pre-skip ordinary ASCII spaces on both the left and right side before falling back to `_Py_ascii_whitespace`.

        Result:

        - Improved direct space-padded microcases, but repeatedly regressed the email-line trim workload and no-pad strings. This changed too much of the common `strip()`/`lstrip()` path.

        Decision:

        - Reject. The broad space pre-skip does not meet the no-regression gate.

        ### E2

        Status: rejected.

        Thesis:

        - Restrict the ordinary-space pre-skip to the right scan while still affecting both `strip()` and `rstrip()`.

        Result:

        - `rstrip_space_padded` remained strong, but `strip_tab_space_padded`, `strip_no_pad`, and Latin-1/noise-sensitive cases still moved negatively. This was safer than E1 but still perturbed `strip()`.

        Decision:

        - Reject. Keep narrowing until the source change is isolated to the profiled target.

        ### E3

        Status: accepted.

        Thesis:

        - Only specialize explicit ASCII `rstrip()` calls. If the last byte is ordinary space, skip the trailing space run before falling back to the full `_Py_ascii_whitespace` table. Leave `strip()` and `lstrip()` control flow unchanged.

        Result:

        - Focused rerun versus `/tmp/unicode_strip_baseline.json`: `rstrip_space_padded` improved `1.293x` (`279.3ns -> 216.1ns`), `textwrap_dedent` was flat (`1.000x`), `strip_space_padded` was flat (`1.004x`), and non-target cases were within about 1.4%.
        - Geomean across the focused corpus was `1.026x`, dominated by the intended `rstrip()` trailing-space win.
        - The change is ASCII-only and falls back to the existing whitespace table for tabs, ASCII control whitespace, Latin-1, and BMP cases.

        Decision:

        - Accept as a narrow, profile-backed proof branch. The win is not broad enough to justify extending to `strip()` or `lstrip()` without better macro evidence.

        ## Validation

        - Focused tests: custom strip guardrail passed; `./python -m test test_str test_string` passed (`192` run, `6` skipped). `test_unicode` is not a module in this checkout, so it was replaced with adjacent string tests.
        - Full suite: `./python -m test -j4` passed: `476 tests OK`, `49,882` run, `2,596` skipped, `5 min 31 sec`.
        - Ecosystem / third-party: not run for promotion; prior `django_template` pyperformance remains blocked in this environment by pinned Django importing removed `distutils`.

        ## Acceptance Decision

        - Decision: accepted.
        - Accepted commit: `16b568756f30e1dc71c800fa4381222692938e5c`
        - Stacked winner commit:

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
