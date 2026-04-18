# Unicode Join Perf Data

Artifacts for `exp-unicode/joinarray-fastpaths`.

## Files

- `unicode_join_usage_scan.py`
  - AST scan over `Lib/`, `Lib/test/`, and the local third-party sample
    environment to inventory `.join(...)` receiver shapes, argument
    shapes, and package concentration.
- `usage-scan.json`
  - Output of the usage inventory.
- `unicode_join_bench.py`
  - Benchmark harness for focused `str.join` micros plus real workloads
    built around Jinja2, Django templates, Django's `join` filter,
    `prompt_toolkit`, and `jsonschema` error formatting.
- `unicode_join_checks.py`
  - Deterministic correctness smoke over the benchmark workloads.
- `baseline.json`
  - Rebuilt-`main` baseline timings.
- `c1_empty_sep_kind.json`
  - Candidate 1: let empty separators stop participating in the
    memcpy-kind gate.
- `c2_first_item_hoist.json`
  - Candidate 2: candidate 1 plus hoist the first item out of the copy
    loops.
- `c3_empty_sep_split.json`
  - Candidate 3: candidate 1 plus explicit `seplen == 0` loop splits.
- `c4_hoist_plus_empty_split.json`
  - Candidate 4: candidate 2 plus explicit `seplen == 0` loop splits.
- `c5_ascii_tiny_sep_store.json`
  - Candidate 5: candidate 2 plus 1-byte direct stores for ASCII
    separators of length 1 or 2.
- `c6_ascii_sep_plus_smalln.json`
  - Candidate 6: candidate 5 plus `seqlen == 2/3` dedicated copy paths.
- `c2_confirm.json`
  - Longer confirm run for the recommended candidate.
- `c5_confirm.json`
  - Longer confirm run for the main runner-up.

## Reproduction

From the branch worktree:

```bash
python3 Misc/unicode-join-perf-data/unicode_join_usage_scan.py \
  > Misc/unicode-join-perf-data/usage-scan.json

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/unicode-join-perf-data/unicode_join_bench.py \
  --label baseline \
  --output Misc/unicode-join-perf-data/baseline.json \
  --samples 5

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/unicode-join-perf-data/unicode_join_checks.py
```

Candidate JSONs were produced by rebuilding the branch after each patch
variant and rerunning `unicode_join_bench.py` with a new `--label` /
`--output` pair.
