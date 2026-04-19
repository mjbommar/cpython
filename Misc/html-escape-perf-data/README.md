# HTML Escape Perf Data

Artifacts for `exp-html/escape-fastpath`.

## Files

- `html_escape_usage_scan.py`
  - AST scan of `Lib/`, `Lib/test/`, and the local third-party sample
    environment to inventory direct `html.escape(...)` call sites.
- `usage-scan.json`
  - Output of the usage inventory.
- `html_escape_bench.py`
  - Benchmark harness for focused `html.escape` micros plus stdlib and
    third-party wrapper workloads around Django, Starlette, Gunicorn,
    and Pygments.
- `html_escape_checks.py`
  - Deterministic correctness smoke over the benchmark workloads and
    semantics-sensitive edge cases such as `str` subclasses.
- `baseline.json`
  - Baseline timings using the current chained-`replace` algorithm.
- `c1_noop_then_baseline.json`
  - Candidate 1: exact-`str` no-op fast path, then current logic.
- `c1_confirm.json`
  - Longer confirm run for the recommended candidate.
- `c2_split_quote_paths.json`
  - Candidate 2: split `quote` / `quote=False` paths plus original-text
    presence tests and conditional replaces.
- `c3_find_conditional.json`
  - Candidate 3: same specialization shape as C2 but using `find()`.
- `c4_any_scan.json`
  - Candidate 4: `any(...)` pre-scan plus current logic.
- `c5_translate.json`
  - Candidate 5: `str.translate()` tables with regex no-op guards.
- `c6_regex.json`
  - Candidate 6: regex substitution.
- `c7_single_pass.json`
  - Candidate 7: single-pass slice/pieces builder.
- `stdlib_confirm.json`
  - Confirm run using the actual patched branch `html.escape`.

## Reproduction

From the branch worktree:

```bash
python3 Misc/html-escape-perf-data/html_escape_usage_scan.py \
  > Misc/html-escape-perf-data/usage-scan.json

PYTHONPATH=/tmp/perf-extra-pkgs /tmp/cpython-main-bench/python \
  Misc/html-escape-perf-data/html_escape_bench.py \
  --label baseline \
  --variant baseline \
  --output Misc/html-escape-perf-data/baseline.json

PYTHONPATH=/tmp/perf-extra-pkgs /tmp/cpython-main-bench/python \
  Misc/html-escape-perf-data/html_escape_checks.py
```

Candidate JSONs were produced by rerunning `html_escape_bench.py` with a
new `--variant` / `--label` / `--output` combination. The final
`stdlib_confirm.json` should be produced with the patched branch on
`PYTHONPATH`, using `--variant stdlib`.
