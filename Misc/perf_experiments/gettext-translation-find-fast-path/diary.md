# gettext translation/find fast path

Branch: `exp-gettext/translation-find-mainline`
Base commit: `5bd5d7b13d6b7e5111aac911148e7894a84b8b1a`
Manifest: `Misc/perf_experiments/gettext-translation-find-fast-path/experiment.json`

## Goal

Archetype: `precomputed snapshot` plus `common-case split`. Broad stacked
discovery showed `Lib/gettext.py:translation/find/_expand_lang` contributing a
real pure-Python cluster, mostly because `argparse` repeatedly calls
`gettext.gettext()` on the no-translation path during parser construction, help
formatting, and error rendering. The first safe shape was to cache the pure
locale expansion work in `_expand_lang(loc)` and return a copy to preserve the
historical mutable-list contract for callers.

## Targets

- `Lib/gettext.py:232 _expand_lang`
- `Lib/gettext.py:489 find`
- `Lib/gettext.py:529 translation`

## Success Criteria

- Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload
  reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked
  winner branch.

## Input Evidence

- Profiles:
  - `/tmp/stacked-discovery-2026-04-24.pstats`
  - stacked discovery attribution:
    - `Lib/gettext.py:529 translation`: `17,272` calls, about `2.171s`
      cumulative
    - `Lib/gettext.py:489 find`: `17,272` calls, about `2.060s`
      cumulative
    - `Lib/gettext.py:232 _expand_lang`: `34,544` calls, about `0.852s`
      cumulative
    - `Lib/gettext.py:628 gettext`: `17,232` calls, about `2.278s`
      cumulative
- Usage scan:
  - dominant callers of `gettext.gettext()` in the same profile were
    `argparse` paths, not just tests:
    - `Lib/argparse.py:1944 __init__`: about `1.028s`
    - `Lib/argparse.py:320 _format_usage`: about `0.350s`
    - `Lib/argparse.py:2875 error`: about `0.273s`
    - `Lib/argparse.py:2084 parse_args`: about `0.138s`
    - `Lib/argparse.py:2472 _match_argument`: about `0.118s`
  - the broad signal was therefore real repeated no-translation lookup work,
    not a thin wrapper illusion local to one benchmark.
- Initial benchmark corpus:
  - `benchmarks/bench_gettext_translation_find.py`
  - cases:
    - `G1_expand_lang`
    - `G2_find_missing_explicit`
    - `G3_find_missing_default_env`
    - `G4_dgettext_missing`
    - `G5_gettext_missing`
    - `G6_argparse_ctor`
    - `G7_argparse_help`
    - `G8_argparse_error`
  - result artifacts:
    - `benchmarks/results/runtime-baseline.json`
    - `benchmarks/results/runtime-cached-expand-lang.json`
    - `benchmarks/results/source-baseline-a.json`
    - `benchmarks/results/source-candidate-a.json`
- Guardrails:
  - `guardrails/check_gettext_translation_semantics.py`
  - result: passed (`gettext translation guardrails: ok`)

## Candidate Ledger

### E1

Status: accepted.

Thesis:

Cache `_expand_lang(loc)` results by original input locale, return a copy on
cache hit, and avoid recomputing the same locale expansion list on repeated
`find()` / `translation()` misses.

Result:

- Runtime monkeypatch proof with cached `_expand_lang`: about `1.728855x`
  geomean.
- Runtime proof details:
  - `G1_expand_lang`: `3,608.6 ns -> 182.4 ns` (`+1878.40%`)
  - `G2_find_missing_explicit`: `23,794.7 ns -> 18,725.8 ns` (`+27.07%`)
  - `G3_find_missing_default_env`: `48,711.4 ns -> 38,635.4 ns` (`+26.08%`)
  - `G4_dgettext_missing`: `50,328.6 ns -> 40,250.6 ns` (`+25.04%`)
  - `G5_gettext_missing`: `50,730.8 ns -> 40,365.8 ns` (`+25.68%`)
  - `G6_argparse_ctor`: `264,631.9 ns -> 222,218.1 ns` (`+19.09%`)
  - `G7_argparse_help`: `651,490.5 ns -> 567,579.7 ns` (`+14.78%`)
  - `G8_argparse_error`: `616,427.8 ns -> 525,843.7 ns` (`+17.23%`)
- Clean source proof with patched `Lib/gettext.py`: about `1.767381x`
  geomean.
- Source proof details:
  - `G1_expand_lang`: `3,763.9 ns -> 174.5 ns` (`+2056.96%`)
  - `G2_find_missing_explicit`: `24,638.2 ns -> 19,252.7 ns` (`+27.97%`)
  - `G3_find_missing_default_env`: `50,202.6 ns -> 39,355.4 ns` (`+27.56%`)
  - `G4_dgettext_missing`: `51,491.0 ns -> 40,827.0 ns` (`+26.12%`)
  - `G5_gettext_missing`: `51,802.3 ns -> 40,642.7 ns` (`+27.46%`)
  - `G6_argparse_ctor`: `270,133.1 ns -> 222,941.4 ns` (`+21.17%`)
  - `G7_argparse_help`: `663,270.5 ns -> 573,085.4 ns` (`+15.74%`)
  - `G8_argparse_error`: `631,392.4 ns -> 526,440.6 ns` (`+19.94%`)

Decision:

Accepted on the clean branch. This is a small reviewable patch with clear
profile attribution, strong source-proof numbers, and low semantic risk.

## Validation

- Guardrails:
  - root runtime guardrail: passed
  - clean branch via `PYTHONPATH` guardrail: passed
  - stacked branch guardrail:
    `check_gettext_translation_semantics.py`: passed
- Focused tests:
  - clean branch:
    - `test_gettext`: passed
    - `test_argparse test_optparse`: passed
    - `test_tools.test_i18n`: passed
  - stacked branch:
    - `test_gettext`: passed
    - `test_argparse test_optparse`: passed
    - `test_tools.test_i18n`: passed
- Full suite:
  - clean branch:
    - `./python -m test -j8`
    - result: passed
    - summary: `49,882` run, `2,623` skipped, `476 tests OK`, `SUCCESS`,
      `4 min 20 sec`
  - stacked branch:
    - `./python -m test -j8`
    - result: passed
    - summary: `49,892` run, `2,620` skipped, `476 tests OK`, `SUCCESS`,
      `4 min 17 sec`
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: stacked winner
- Accepted commit: `0832cc79cbc`
- Stacked winner commit: `0497f2871cf`

## Notes

- A more aggressive idea, such as negative caching for missing locale files,
  was intentionally deferred. `_expand_lang()` caching already captured most of
  the broad signal with a much smaller semantics surface.
- Current phase: `stacked`
- Next gate: include this winner in the next broad stacked-vs-main aggregate
  refresh.
