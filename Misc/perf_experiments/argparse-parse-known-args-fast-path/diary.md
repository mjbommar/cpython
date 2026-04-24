# argparse parse-known-args fast path

Branch: `exp-argparse/parse-known-mainline`
Base commit: `168e223bf51e795a854f3b39dc7f53c97494131f`
Manifest: `Misc/perf_experiments/argparse-parse-known-args-fast-path/experiment.json`

## Goal

Archetype: `common-case split` plus `control-flow lifting`. Fresh broad
discovery after the gettext win still showed an `argparse` parse cluster, with
the real cumulative work centered in `_parse_known_args2()` and
`_parse_known_args()` rather than the public wrappers. The first hypothesis was
that the common no-`fromfile_prefix_chars`, no-mutually-exclusive-groups path
could skip conflict-map construction, `seen_non_default_actions` bookkeeping,
and required-group post-checks.

## Targets

- `Lib/argparse.py:2097 _parse_known_args2`
- `Lib/argparse.py:2135 _parse_known_args`

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
    - `Lib/argparse.py:2097 _parse_known_args2`: `5,637` calls,
      about `2.223s` cumulative
    - `Lib/argparse.py:2135 _parse_known_args`: `5,637` calls,
      about `1.219s` cumulative
    - `Lib/argparse.py:2472 _match_argument`: `3,480` calls,
      about `0.201s` cumulative
- Usage scan:
  - `_parse_known_args2()` was driven almost entirely by
    `parse_known_args()` / `parse_known_intermixed_args()`
  - `parse_args()` traffic in the same profile was heavily dominated by
    `test_argparse`, but `_parse_known_args2()` / `_parse_known_args()` remain
    public-library choke points and are used in non-test stdlib code too
  - default `ArgumentParser` objects have:
    - `fromfile_prefix_chars is None`
    - `len(_mutually_exclusive_groups) == 0`
  - that made the no-mutex/no-fromfile split the most plausible first probe
- Initial benchmark corpus:
  - `benchmarks/bench_argparse_parse_known_args.py`
  - cases:
    - `A1_simple_parse_known_args`
    - `A2_simple_parse_args`
    - `A3_defaults_namespace`
    - `A4_option_heavy`
    - `A5_intermixed`
    - `A6_mutex_control`
    - `A7_fromfile_control`
  - result artifacts:
    - `benchmarks/results/runtime-baseline.json`
    - `benchmarks/results/runtime-no-mutex-fast-path.json`
    - `benchmarks/results/source-baseline-a.json`
    - `benchmarks/results/source-candidate-a.json`
- Guardrails:
  - `guardrails/check_argparse_parse_known_args_semantics.py`
  - result: passed (`argparse parse-known-args guardrails: ok`)

## Candidate Ledger

### E1

Status: rejected.

Thesis:

When the parser has no `fromfile_prefix_chars` and no mutually exclusive
groups, skip `action_conflicts` construction, `seen_non_default_actions`
tracking, and the required-group post-check.

Result:

- Runtime proof via monkeypatch helper (`helpers.py`): about `+5.20%` geomean.
- Runtime details:
  - `A1_simple_parse_known_args`: `+7.84%`
  - `A2_simple_parse_args`: `+7.52%`
  - `A3_defaults_namespace`: `+8.12%`
  - `A4_option_heavy`: `+7.96%`
  - `A5_intermixed`: `+6.78%`
  - `A6_mutex_control`: `-0.38%`
  - `A7_fromfile_control`: `-0.99%`
- Clean source proof on the worktree patch: about `+1.38%` geomean.
- Source details:
  - `A1_simple_parse_known_args`: `+8.97%`
  - `A2_simple_parse_args`: `+0.61%`
  - `A3_defaults_namespace`: `-3.47%`
  - `A4_option_heavy`: `+4.00%`
  - `A5_intermixed`: `+2.63%`
  - `A6_mutex_control`: `-4.04%`
  - `A7_fromfile_control`: `+1.55%`

Decision:

Rejected at source proof. The source patch was too weak and too mixed once the
benchmark monkeypatch was turned into a realistic code change.

## Validation

- Guardrails:
  - runtime guardrail: passed
  - source-proof guardrail against the worktree `Lib/argparse.py`: passed
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

- This family is a good example of why the process insists on source proof
  before a clean-branch validation run. The runtime helper looked good enough
  to tempt a promotion, but the actual source patch did not justify more work.
- Keep rejected ideas here too so the branch remains useful research.
