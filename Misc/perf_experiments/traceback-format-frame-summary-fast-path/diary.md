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
          - `benchmarks/bench_traceback_format.py`
          - baseline artifact:
            `benchmarks/results/runtime-baseline.json`
          - cases:
            - `T1_frame_simple`
            - `T2_frame_locals`
            - `T3_frame_caret`
            - `T4_stack_simple`
            - `T5_stack_recursive`
            - `T6_te_simple`
            - `T7_te_caret`
            - `T8_te_locals`
            - `T9_format_exception_simple`
            - `T10_format_exception_caret`
          - first baseline highlights:
            - `T1_frame_simple`: about `57.4 us`
            - `T3_frame_caret`: about `85.6 us`
            - `T4_stack_simple`: about `126.0 us`
            - `T6_te_simple`: about `141.7 us`
            - `T10_format_exception_caret`: about `224.9 us`
        - Guardrails:
          - `guardrails/check_traceback_format_semantics.py`
          - result: `traceback format guardrails: ok`

        ## Candidate Ledger

        ### E1

        Status: accepted.

        Thesis:

        Split `StackSummary.format_frame_summary()` by the dominant
        `colorize=False` path and stop paying the no-color theme setup and
        colorized-caret rewriting costs on the common non-color path.

        Result:

        - Runtime monkeypatch proof (`frame_no_color` vs
          `runtime-baseline.json`): about `+2.64%` geomean.
        - Source proof (`source-baseline-a.json` vs
          `source-candidate-a.json`): about `+4.35%` geomean, all ten focused
          cases positive.
        - Source proof details:
          - `T1_frame_simple`: `57,954.2 ns -> 55,313.2 ns` (`+4.77%`)
          - `T2_frame_locals`: `61,963.0 ns -> 57,500.7 ns` (`+7.76%`)
          - `T3_frame_caret`: `85,842.4 ns -> 83,532.5 ns` (`+2.77%`)
          - `T4_stack_simple`: `128,374.1 ns -> 122,127.6 ns` (`+5.11%`)
          - `T5_stack_recursive`: `636,990.2 ns -> 612,074.7 ns` (`+4.07%`)
          - `T6_te_simple`: `143,529.1 ns -> 137,702.5 ns` (`+4.23%`)
          - `T7_te_caret`: `170,827.7 ns -> 165,906.8 ns` (`+2.97%`)
          - `T8_te_locals`: `150,669.4 ns -> 143,011.1 ns` (`+5.36%`)
          - `T9_format_exception_simple`: `196,372.9 ns -> 189,711.2 ns`
            (`+3.51%`)
          - `T10_format_exception_caret`: `226,930.8 ns -> 220,249.8 ns`
            (`+3.03%`)

        Decision:

        Accepted on the clean branch as the smallest coherent positive shape.

        ### E2

        Status: rejected.

        Thesis:

        Split `StackSummary.format()` so the no-color path avoids repeatedly
        passing `colorize=False` and lifts some loop bookkeeping.

        Result:

        - Runtime monkeypatch proof (`stack_no_color`): about `-1.02%`
          geomean.

        Decision:

        Rejected before source work. The split did not carry its own weight.

        ### E3

        Status: rejected.

        Thesis:

        Combine `E1` and `E2` to see if the frame-level fast path becomes more
        valuable when paired with a no-color `StackSummary.format()` split.

        Result:

        - Runtime monkeypatch proof (`frame_stack_no_color`): about `+2.73%`
          geomean.

        Decision:

        Rejected as a separate patch. It was only noise-sized above `E1`, so
        the campaign bias favored carrying the smaller reviewable patch into
        source proof first.

        ## Validation

        - Guardrails:
          - exact baseline-vs-patched output compare on benchmark fixtures:
            passed
          - `guardrails/check_traceback_format_semantics.py`: passed
        - Focused tests:
          - `test_traceback`: passed
          - `test_exceptions test_warnings`: passed
          - `test_logging test_pdb`: passed
        - Full suite:
          - clean branch full suite: `49,882` run, `2,623` skipped,
            `SUCCESS` in `4 min 20 sec`
        - Stacked validation:
          - stacked guardrail:
            `check_traceback_format_semantics.py`: passed
          - stacked focused tests:
            `test_traceback`: passed
          - stacked focused tests:
            `test_exceptions test_warnings`: passed
          - stacked focused tests:
            `test_logging test_pdb`: passed
          - stacked full suite: `49,892` run, `2,620` skipped,
            `SUCCESS` in `4 min 17 sec`
        - Ecosystem / third-party:
          - not run

        ## Acceptance Decision

        - Decision: stacked winner
        - Accepted commit: `67cf6742853`
        - Stacked winner commit: `6eea811f501`

        ## Notes

        - Current phase: `stacked`
        - Next gate: include this winner in the next broad stacked-vs-main
          aggregate benchmark refresh.
        - Keep rejected ideas here too so the branch remains useful research.
