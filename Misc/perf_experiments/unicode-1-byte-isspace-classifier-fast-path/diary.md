        # Unicode 1-byte isspace classifier fast path

        Branch: `exp-unicode/isspace-1byte-mainline`
        Base commit: `ad7d3616c6cc21c5ec032a726e4c5e819628aa6e`
        Manifest: `Misc/perf_experiments/unicode-1-byte-isspace-classifier-fast-path/experiment.json`

        ## Goal

        Long 1-byte str.isspace() calls repeatedly enter generic Unicode whitespace checks; a single-pass 1-byte whitespace bitset should reduce parser/text workload runtime while preserving full Unicode semantics.

        ## Targets

        - Objects/unicodeobject.c:11874 unicode_isspace_impl

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Archetype: prepared-search / input-shape snapshot (`perf_patterns.md` section 1.3a). This mirrors the StringZilla byteset-classifier shape, but must preserve CPython's full one-byte whitespace semantics.
        - Profiles: `./python -m cProfile -o /tmp/isspace_test_email.prof -m test test_email` showed `str.isspace` present but small (`5761` calls, about `0.000926s` self time). Adjacent string trimming paths were larger: `strip`, `lstrip`, and `rstrip`.
        - Usage scan: stdlib users include `Lib/email/header.py`, `Lib/_markupbase.py`, `Lib/textwrap.py`, `Lib/traceback.py`, `Lib/pdb.py`, `_pyrepl`, `http.client`, `sqlite3.__main__`, `Tools/clinic`, and `Tools/peg_generator`.
        - Initial benchmark corpus: focused synthetic `isspace` cases plus stdlib-shaped `line_filter` and `textwrap.dedent`.
        - Guardrails: one-byte table must match `chr(ch).isspace()` for all `0 <= ch < 256`, including U+001C..U+001F, U+0085, and U+00A0. Wider Unicode paths must remain unchanged.

        ## Candidate Ledger

        ### E1

        Status: rejected.

        Thesis:

        - Use a four-word one-byte whitespace bitset in `unicode_isspace_impl` for every `PyUnicode_1BYTE_KIND` string.

        Result:

        - Rejected before commit. The bitset preserved one-byte semantics but regressed ASCII common cases by about 11-13% while improving Latin-1 whitespace cases. ASCII is the dominant realistic path, so this failed the input-shape gate.

        Decision:

        - Do not promote. The StringZilla-style classifier needs an ASCII guard or a different integration point.

        ### E2

        Status: rejected.

        Thesis:

        - Restrict the same one-byte whitespace bitset to non-ASCII one-byte strings, leaving ASCII on the existing `_Py_ascii_whitespace` path.

        Result:

        - Semantic guardrails passed.
        - Focused rerun versus `/tmp/unicode_isspace_baseline.json`: `isspace_latin1_true` improved `1.60x`, `isspace_latin1_false_tail` improved `1.58x`, ASCII/BMP stayed flat, `line_filter` was `1.003x`, and `textwrap_dedent` was `1.006x`.
        - Geomean speedup was `1.128x`, but this was dominated by synthetic Latin-1 whitespace strings. The realistic stdlib-shaped cases did not show a material total-runtime win.

        Decision:

        - Reject and leave the source unchanged. This is a valid narrow primitive win, but it does not meet the campaign bar for total-runtime improvement or stacked-winner promotion. The stronger follow-up target is the adjacent `strip` / `lstrip` / `rstrip` surface exposed by the same `test_email` profile.

        ## Validation

        - Focused tests: not run after rejection because no source change remains.
        - Full suite: not run after rejection because no source change remains.
        - Ecosystem / third-party: `pyperformance django_template` remains blocked in this environment by pinned Django importing removed `distutils`; no promotion decision depends on it.

        ## Acceptance Decision

        - Decision: rejected.
        - Accepted commit:
        - Stacked winner commit:

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Future whitespace work should prioritize full trimming loops over `isspace()` alone. The profile signal was substantially larger for `strip`-family methods than for `isspace`.
