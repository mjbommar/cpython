# pickletools genops fast path

Branch: `exp-pickletools/genops-mainline`
Base commit: `9fab602d28a89f6f40d2315f4ad7e2c7a3144110`
Manifest: `Misc/perf_experiments/pickletools-genops-fast-path/experiment.json`

## Goal

Archetype: representation shift plus loop-invariant hoisting.
`pickletools._genops()` still spends real stacked-profile time decoding one-byte
opcodes and doing text-key dict lookup on every step. The likely leverage is a
byte-indexed opcode table plus localized hot-loop bindings that reduce per-op
overhead without changing generator semantics.

## Targets

- `Lib/pickletools.py:2268 _genops`

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
    - `Lib/pickletools.py:2268 _genops`: about `1.657s` cumulative
    - about `387,470` calls on the stacked discovery profile
- Usage scan:
  - direct test users are concentrated in `Lib/test/test_pickletools.py` and
    `Lib/test/pickletester.py`
  - downstream stdlib consumers are mostly `pickletools.optimize()` and
    `pickletools.dis()`, both of which route through `_genops()`
  - the hot-loop waste is obvious in the current implementation:
    `read(1)` -> `code.decode("latin-1")` -> `code2op.get(...)` for every
    opcode
- Initial benchmark corpus:
  - `G1_genops_small_list`
  - `G2_genops_int_tuple`
  - `G3_genops_nested_dict`
  - `G4_genops_end_frame_heavy`
  - `G5_genops_no_tell_proto2`
  - `G6_optimize_frame_heavy`
  - `G7_dis_nested_dict`
- Guardrails:
  - `check_pickletools_genops_semantics.py`
  - verifies `_genops()` tuple streams with and without `yield_end_pos`
  - verifies `NoTellReader` behavior
  - verifies `genops()`, `optimize()`, and `dis()` outputs remain identical

## Candidate Ledger

### E1

Status: accepted.

Thesis:

- Replace per-opcode text decoding with a private byte-indexed opcode table and
  split the hot loop by `tell()` availability and `yield_end_pos`, so the
  common path avoids both `code.decode("latin-1")` and the per-iteration branch
  on `yield_end_pos`.

Result:

- Runtime proof on stacked baseline:
  - `G1_genops_small_list`: `+19.99%`
  - `G2_genops_int_tuple`: `+20.37%`
  - `G3_genops_nested_dict`: `+13.59%`
  - `G4_genops_end_frame_heavy`: `+17.98%`
  - `G5_genops_no_tell_proto2`: `+21.45%`
  - `G6_optimize_frame_heavy`: `+8.75%`
  - `G7_dis_nested_dict`: `+5.35%`
  - geomean: `1.152053x` (`+15.21%`)
- Clean same-worktree source A/B:
  - `G1_genops_small_list`: `42267.9 -> 36829.8 ns` (`+14.77%`)
  - `G2_genops_int_tuple`: `101210.6 -> 89152.6 ns` (`+13.53%`)
  - `G3_genops_nested_dict`: `521779.3 -> 483685.8 ns` (`+7.88%`)
  - `G4_genops_end_frame_heavy`: `222455.7 -> 201198.6 ns` (`+10.57%`)
  - `G5_genops_no_tell_proto2`: `245168.7 -> 210803.4 ns` (`+16.30%`)
  - `G6_optimize_frame_heavy`: `479188.6 -> 460226.2 ns` (`+4.12%`)
  - `G7_dis_nested_dict`: `3551914.4 -> 3544605.1 ns` (`+0.21%`)
  - geomean: `1.094843x` (`+9.48%`)

Decision:

- Accept.
- The source-level win compressed versus the runtime monkeypatch, but it stayed
  comfortably above the acceptance bar and remained positive in every direct
  `_genops()` workload plus `optimize()`.

## Validation

- Focused tests:
  - clean guardrail:
    `check_pickletools_genops_semantics.py`: `ok`
  - clean focused tests:
    `test_pickletools`: passed
  - clean focused tests:
    `test_pickle test_picklebuffer`: passed
- Full suite:
  - clean branch: `49,892` run, `2,623` skipped, `SUCCESS` in `4 min 22 sec`
- Ecosystem / third-party:
- Stacked validation:
  - stacked guardrail:
    `check_pickletools_genops_semantics.py`: `ok`
  - stacked focused tests:
    `test_pickletools`: passed
  - stacked focused tests:
    `test_pickle test_picklebuffer`: passed
  - stacked branch: `49,892` run, `2,620` skipped, `SUCCESS` in
    `4 min 18 sec`

## Acceptance Decision

- Decision: accepted
- Accepted commit: `f8738c1dcd8`
- Stacked winner commit: `e9be1a19d06`

## Notes

- The first source patch accidentally exposed `byte2op` as a public module
  global, which broke `test_pickletools` via `pickletools.__all__`. Renaming it
  to `_byte2op` fixed the regression without changing the measured result.
- `pickletools.dis()` was nearly flat at source level, so the justification for
  acceptance is the direct `_genops()` / `optimize()` win, not a claim that all
  higher-level consumers move equally.
- Current phase: `stacked`
- Next gate: none; this family is fully promoted.
