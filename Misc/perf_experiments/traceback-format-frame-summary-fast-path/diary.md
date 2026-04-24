        # traceback format frame summary fast path

        Branch: `exp-traceback/frame-summary-mainline`
        Base commit: `ad7d3616c6cc21c5ec032a726e4c5e819628aa6e`
        Manifest: `Misc/perf_experiments/traceback-format-frame-summary-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split plus control-flow lifting. Fresh stacked discovery still shows traceback formatting as a real pure-Python cluster: StackSummary.format(), StackSummary.format_frame_summary(), and traceback.format(). Most formatted frames are on the common no-colorize, no-locals path, and many miss the full caret-anchor machinery. Splitting that common path away from the heavy caret/color/locals logic may reduce traceback formatting overhead without changing rendered output.

        ## Targets

        - Lib/traceback.py:546 StackSummary.format_frame_summary
- Lib/traceback.py:763 StackSummary.format
- Lib/traceback.py:1577 TracebackException.format

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - `/tmp/stacked-discovery-2026-04-24.pstats`
          - current curated stacked-branch discovery still shows a real
            traceback cluster:
            - `Lib/traceback.py:1577 format`: about `2.00s` cumulative
            - `Lib/traceback.py:763 format`: about `1.83s`
            - `Lib/traceback.py:546 format_frame_summary`: about `1.79s`
        - Usage scan:
          - archetype: `common-case split` plus `control-flow lifting`
          - `format_frame_summary()` is a better fit than `argparse`, whose
            hot path in this profile is likely dominated by one-shot CLI /
            test-local parsing
          - `gettext` was also considered and deferred because the visible hot
            chain (`gettext -> dgettext -> translation -> find`) currently
            looks closer to a cached wrapper stack than a clear internal
            algorithmic win
          - the likely leverage point is the common no-colorize, no-locals,
            limited-caret path inside `format_frame_summary()`
        - Initial benchmark corpus:
          - pending
        - Guardrails:
          - pending

        ## Candidate Ledger

        ### E1

        Status: pending.

        Thesis:

        -

        Result:

        -

        Decision:

        -

        ## Validation

        - Focused tests:
        - Full suite:
        - Ecosystem / third-party:

        ## Acceptance Decision

        - Decision:
        - Accepted commit:
        - Stacked winner commit:

        ## Notes

        - Current phase: `usage-scan`
        - Next gate: define focused benchmark corpus and guardrails before any
          source branch exists.
        - Keep rejected ideas here too so the branch remains useful research.
