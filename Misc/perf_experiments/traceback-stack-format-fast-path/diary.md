# traceback stack format fast path

Branch: `exp-traceback/stack-format-mainline`
Base commit: `2b93536ee010528803a7ddf8f9a2149130a26855`
Manifest: `Misc/perf_experiments/traceback-stack-format-fast-path/experiment.json`

## Goal

Archetype: `common-case split` plus `control-flow lifting`.

After the earlier `format_frame_summary()` winner, fresh stacked discovery still
showed cumulative cost in:

- `Lib/traceback.py:763 StackSummary.format`: about `1.825s`
- `Lib/traceback.py:1577 TracebackException.format`: about `2.005s`

The thesis for this follow-up family was that the remaining cost might still
contain a simple common path:

- `TracebackException.format()` on the ordinary no-chain, no-group case
- `StackSummary.format()` on the common no-repeated-adjacent-frames case

## Targets

- `Lib/traceback.py:763 StackSummary.format`
- `Lib/traceback.py:1577 TracebackException.format`

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
  - stacked discovery attribution on the current stacked branch:
    - `Lib/traceback.py:1577 format`: about `2.005s`
    - `Lib/traceback.py:763 format`: about `1.825s`
- Usage scan:
  - the prior traceback family already proved `format_frame_summary()` was a
    real winner
  - this follow-up family scoped only the remaining orchestrator layers, not
    the already-optimized frame formatter
- Initial benchmark corpus:
  - `benchmarks/bench_traceback_stack_format.py`
  - cases:
    - `T1_stack_simple`
    - `T2_stack_recursive`
    - `T3_te_simple`
    - `T4_te_locals`
    - `T5_te_caret`
    - `T6_te_chain`
    - `T7_format_exception_simple`
    - `T8_format_exception_caret`
- Guardrails:
  - `guardrails/check_traceback_stack_format_semantics.py`
  - result: passed (`traceback stack format guardrails: ok`)

## Candidate Ledger

### E1

Status: rejected.

Thesis:

Add a `TracebackException.format()` fast path for the common:

- `chain=True`
- `_ctx is None`
- no `__cause__`
- no `__context__`
- no exception group

shape, avoiding the temporary output list and reversed chain walk.

Result:

- Runtime proof only: about `+0.02%` geomean.
- Details:
  - `T1_stack_simple`: `-0.45%`
  - `T2_stack_recursive`: `+0.20%`
  - `T3_te_simple`: `+0.64%`
  - `T4_te_locals`: `+0.86%`
  - `T5_te_caret`: `+0.18%`
  - `T6_te_chain`: `-1.93%`
  - `T7_format_exception_simple`: `+0.59%`
  - `T8_format_exception_caret`: `+0.09%`

Decision:

Rejected. The shape was effectively flat and introduced a real regression on
the chained-exception case.

### E2

Status: rejected.

Thesis:

Add a `StackSummary.format()` fast path for the common case where adjacent
frames are not duplicates, and only fall back to the original recursive-repeat
bookkeeping once a repeated frame is actually encountered.

Result:

- Runtime proof only: about `-2.25%` geomean.
- Details:
  - `T1_stack_simple`: `-1.80%`
  - `T2_stack_recursive`: `-2.05%`
  - `T3_te_simple`: `-1.79%`
  - `T4_te_locals`: `-0.68%`
  - `T5_te_caret`: `-2.46%`
  - `T6_te_chain`: `-4.05%`
  - `T7_format_exception_simple`: `-2.23%`
  - `T8_format_exception_caret`: `-2.90%`

Decision:

Rejected immediately. The fallback structure and extra control flow cost more
than the skipped duplicate-frame bookkeeping.

## Validation

- Guardrails:
  - runtime guardrail: passed
- Focused tests:
  - not run
- Full suite:
  - not run
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: rejected
- Accepted commit:
- Stacked winner commit:

## Notes

- Current phase: `rejected`
- This follow-up family did the right thing by closing quickly. The remaining
  traceback orchestrator cost does not appear to hide a cheap common-case win.
- If traceback is revisited again, it should start from a new profile and a
  materially different shape, not from more bookkeeping rewrites of
  `StackSummary.format()` or `TracebackException.format()`.
