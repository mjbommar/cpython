# Initialize Locals Perf Data

Artifacts for `exp-ceval/initialize-locals-fastpath`.

## Files

- `initialize_locals_usage_scan.py`
  - AST scan over `Lib/` and `/tmp/perf-extra-pkgs` to inventory call
    shapes and function signature shapes relevant to `initialize_locals`
    and adjacent call setup.
- `usage-scan.json`
  - Output of the call-shape inventory.
- `initialize_locals_bench.py`
  - Benchmark harness covering focused Python-call micros plus real
    Jinja2, Django, `jsonschema`, and Celery eager workloads.
- `initialize_locals_checks.py`
  - Deterministic correctness smoke over the micro and real workloads.
- `baseline.json`
  - Rebuilt-`main` baseline timings.
- `c1_memcpy_copy.json`
  - Candidate 1: replace the positional local copy loop with `memcpy`.
- `c2_exact_positional_fastpath.json`
  - Candidate 2: candidate 1 plus exact simple-signature early return.
- `c3_defaults_fastpath.json`
  - Candidate 3: candidate 2 plus trailing-defaults early return.
- `c4_no_keyword_split.json`
  - Candidate 4: dedicated no-keyword helper path with bulk positional copy.
- `c5_no_keyword_plus_exact.json`
  - Candidate 5: candidate 4 plus exact-signature early return.
- `c6_no_keyword_small_copy_switch.json`
  - Candidate 6: candidate 4 plus `0-4` positional manual copy switch.
- `c7_no_keyword_small_copy_plus_vector.json`
  - Candidate 7: candidate 6 plus `_PyEval_Vector` small-arg copy switch.
- `c8_small_copy_everywhere.json`
  - Candidate 8: candidate 7 plus small-copy switch in the generic
    keyword-capable path.
- `c7_confirm.json`
  - Longer confirm run for the recommended candidate.
- `c8_confirm.json`
  - Longer confirm run for the main runner-up.

## Reproduction

From the branch worktree:

```bash
python3 Misc/initialize-locals-perf-data/initialize_locals_usage_scan.py \
  > Misc/initialize-locals-perf-data/usage-scan.json

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/initialize-locals-perf-data/initialize_locals_checks.py

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/initialize-locals-perf-data/initialize_locals_bench.py \
  --label baseline \
  --output Misc/initialize-locals-perf-data/baseline.json \
  --samples 5
```

Candidate JSONs were produced by rebuilding the branch after each patch
variant and rerunning `initialize_locals_bench.py` with a new
`--label` / `--output` pair.
