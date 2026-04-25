        # Unicode 1-byte islower/isupper classifier fast path

        Branch: `exp-unicode/islower-isupper-1byte-mainline`
        Base commit: `ad7d3616c6cc21c5ec032a726e4c5e819628aa6e`
        Manifest: `Misc/perf_experiments/unicode-1-byte-islower-isupper-classifier-fast-path/experiment.json`

        ## Goal

        Long 1-byte str.islower()/str.isupper() calls repeatedly enter generic Unicode ctype helpers; a single-pass 1-byte bitset classifier should reduce total runtime in string-heavy workloads while preserving wider-Unicode semantics.

        ## Targets

        - Objects/unicodeobject.c:11731 unicode_islower_impl
- Objects/unicodeobject.c:11775 unicode_isupper_impl

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - `Misc/perf_patterns.md` §1.3a records this exact StringZilla-style
            1-byte classifier shape as a prior uncommitted win.
          - Recent stacked regrtest profiles do not surface this as a broad
            leaf hotspot, so this family is being treated as a low-risk string
            primitive improvement with macro smoke checks rather than a
            regrtest-wide runtime claim.
        - Usage scan:
          - `rg "\\.islower\\(|\\.isupper\\(" Lib Tools -g '*.py'`
          - Stdlib consumers include `socket.py`, `signal.py`, `pickle.py`,
            `Tools/clinic/libclinic/cli.py`, `Tools/build/generate_token.py`,
            `_pyrepl`, and `collections.UserString` wrappers.
          - Common stdlib shapes are short ASCII names/constants; long-string
            value comes from the primitive itself and downstream string-heavy
            workloads.
        - Initial benchmark corpus:
          - `benchmarks/bench_islower_isupper.py`
          - Regimes: long ASCII true/false/uncased, long Latin-1 true/false,
            BMP guard cases, and a stdlib-style name-filter loop.
        - Guardrails:
          - `guardrails/check_islower_isupper.py`
          - `./python -m test test_str test_string test_unicodedata -j1`

        ## Candidate Ledger

        ### E1

        Status: accepted for full-suite validation.

        Thesis:

        - Add exact 1-byte fast paths for `str.islower()` and `str.isupper()`
          using local 256-bit classification sets and a single pass over
          `PyUnicode_1BYTE_DATA`.
        - Preserve the existing generic Unicode loop for 2-byte and 4-byte
          strings.
        - This is exact for 1-byte Unicode because the bitsets match current
          CPython classification for all 256 code points and there are no
          titlecase-only code points below U+0100.

        Result:

        - Focused same-worktree A/B, best time per call:
          - `islower_ascii_true`: `386778 ns -> 119251 ns`, `3.24x`
          - `islower_ascii_false_tail`: `386918 ns -> 122357 ns`, `3.16x`
          - `islower_ascii_uncased`: `646584 ns -> 128702 ns`, `5.02x`
          - `islower_latin1_true`: `373645 ns -> 115474 ns`, `3.24x`
          - `islower_latin1_false_tail`: `376414 ns -> 117170 ns`, `3.21x`
          - `isupper_ascii_true`: `421092 ns -> 119556 ns`, `3.52x`
          - `isupper_ascii_false_tail`: `420194 ns -> 122567 ns`, `3.43x`
          - `isupper_ascii_uncased`: `707422 ns -> 128277 ns`, `5.51x`
          - `isupper_latin1_true`: `392057 ns -> 111659 ns`, `3.51x`
          - `isupper_latin1_false_tail`: `395557 ns -> 115281 ns`, `3.43x`
          - `stdlib_name_filters`: `1675172 ns -> 1224972 ns`, `1.37x`
          - BMP guard cases were effectively flat: `islower_bmp_true` `1.00x`,
            `isupper_bmp_true` `1.06x`.
        - Focused geomean across all regimes: `2.79x`.
        - pyperformance fast smoke on candidate:
          - `json_dumps`: `11.7 ms +- 0.4 ms`
          - `json_loads`: `31.5 us +- 0.7 us`
          - `regex_compile`: `150 ms +- 3 ms`
          - These are smoke coverage only; no broad-panel claim is made.
        - `django_template` could not run because pinned Django 3.2.4 imports
          removed `distutils` on this 3.15 build.

        Decision:

        - Keep E1 and run full suite. The patch is small, semantics-local, and
          materially improves the targeted primitive and a stdlib-style wrapper
          loop without moving wider Unicode onto a new path.

        ## Validation

        - Focused tests:
          - `./python Misc/perf_experiments/unicode-1-byte-islower-isupper-classifier-fast-path/guardrails/check_islower_isupper.py`
            passed.
          - `./python -m test test_str test_string test_unicodedata -j1`
            passed: `260` tests run, `13` skipped.
        - Full suite:
          - `./python -m test -j4` passed: `476` tests OK, `49,882` run,
            `2,596` skipped, `5 min 31 sec`.
        - Ecosystem / third-party:
          - pyperformance fast smoke passed for `json_dumps`, `json_loads`,
            and `regex_compile`.
          - `django_template` blocked by benchmark dependency compatibility,
            not by this patch.
        - Stacked validation:
          - Source commit `2ac95e70c25` on `exp-combined-winners-local`.
          - Stacked guardrails passed.
          - `./python -m test test_str test_string test_unicodedata -j1`
            passed.
          - `./python -m test -j4` passed: `476` tests OK, `49,892` run,
            `2,620` skipped, `5 min 32 sec`.

        ## Acceptance Decision

        - Decision: accepted for proof-branch commit and stacked promotion.
        - Accepted commit: `db57b3a52a6`
        - Stacked winner commit: `2ac95e70c25`

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
