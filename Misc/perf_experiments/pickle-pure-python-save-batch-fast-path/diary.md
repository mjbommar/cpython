        # pickle pure-Python save batch fast path

        Branch: `exp-pickle/save-mainline`
        Base commit: `01b070756168ca23ae0af051b2fda562d40c3361`
        Manifest: `Misc/perf_experiments/pickle-pure-python-save-batch-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split plus control-flow lifting. Fresh ranked review still leaves pure-Python pickle save-side hotspots in Pickler.save(), save_list(), and _batch_appends(). The likely leverage is in exact-list/common-batch paths, not another broad reducer-dispatch rewrite.

        ## Targets

        - Lib/pickle.py:562 Pickler.save
- Lib/pickle.py:1024 save_list
- Lib/pickle.py:1037 _batch_appends

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - `/tmp/stacked-discovery-2026-04-24.pstats`
          - stacked discovery attribution:
            - `Lib/pickle.py:581 save`: about `5.501s` cumulative
            - `Lib/pickle.py:1087 save_list`: about `4.043s`
            - `Lib/pickle.py:1028 save_tuple`: about `3.559s`
            - `Lib/pickle.py:1179 save_dict`: about `1.699s`
            - `Lib/pickle.py:522 memoize`: about `1.084s`
            - `Lib/pickle.py:1143 _batch_appends`: about `0.412s`
        - Usage scan:
          - verified directly against `cpython-combined-winners`: the stacked
            baseline already includes the earlier pure-Python pickle save-side
            winner set from `exp-pickle/4-pure-python-exact-containers`
            (`_batch_appends_exact`, `_batch_setitems_exact`, atomic
            `save()` fast paths, inlined `memoize()`, and the `bytes`
            fast path)
          - the remaining save-side signal is broad enough to justify a fresh
            family even after the older exact-type `_pickle` wrapper winner
          - `save_list()` dominates because it calls back into `save()` for
            every element, so the first worthwhile shapes are likely exact-list
            common paths or batch-append control-flow cleanup rather than more
            read-side work
        - Initial benchmark corpus:
        - Guardrails:

        ## Candidate Ledger

        ### E1

        Status: accepted.

        Thesis:

        - Specialize `_batch_appends_exact()` for exact `_Pickler` dumping
          homogeneous exact-`int` lists, so the existing exact-list binary fast
          path bypasses per-item `save()` dispatch and calls `save_long()`
          directly while preserving the current batch snapshot behavior.

        Result:

        - Runtime monkeypatch proof on stacked baseline:
          - `exact_int_lists`: about `1.1805x` geomean (`+18.05%`)
          - `exact_int_lists_min8`: about `1.1687x` geomean (`+16.87%`)
        - Clean same-worktree reduced source A/B:
          - `S1_list_of_ints_10k_dump`: `4891901.3 -> 3405407.5 ns`
            (`+43.65%`)
          - `S2_list_of_strs_1k_dump`: `1040597.0 -> 1028427.1 ns`
            (`+1.18%`)
          - `S3_nested_list_of_dicts_dump`: `2695446.5 -> 2651966.2 ns`
            (`+1.64%`)
          - `S4_deep_list_dump`: `2797169.6 -> 2053790.2 ns`
            (`+36.20%`)
          - `S5_mixed_scalar_list_dump`: `827656.1 -> 859559.6 ns`
            (`-3.71%`)
          - `S6_bool_list_dump`: `1357527.0 -> 1377107.6 ns`
            (`-1.42%`)
          - `S7_small_int_run_dump`: `46224.3 -> 28473.8 ns`
            (`+62.34%`)
          - geomean: `1.175447x` (`+17.54%`)

        Decision:

        - Accept.
        - The no-threshold exact-`int` shape is strong enough at source level
          to justify promotion. The narrow regressions on mixed/bool lists are
          small and expected because those shapes fall through the new probe.

        ## Validation

        - Focused tests:
          - Guardrail passed on clean branch:
            `pickle pure save batch guardrails: ok`
          - `test_pickle test_picklebuffer test_pickletools`: passed
          - `test_copy test_copyreg`: passed
          - `test_shelve`: passed
        - Full suite:
          - clean branch: `49,892` run, `2,620` skipped, `SUCCESS` in
            `4 min 22 sec`
        - Ecosystem / third-party:
        - Stacked validation:
          - guardrail passed on stacked branch:
            `pickle pure save batch guardrails: ok`
          - `test_pickle test_picklebuffer test_pickletools`: passed
          - `test_copy test_copyreg test_shelve`: passed
          - stacked branch: `49,892` run, `2,621` skipped, `SUCCESS` in
            `4 min 19 sec`

        ## Acceptance Decision

        - Decision: accepted
        - Accepted commit: `b76535a0ca8`
        - Stacked winner commit: `f9d0024b371`

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Current phase: `stacked`
        - Next gate: none; this family is fully promoted.
