This directory holds benchmark and inventory artifacts for the
`exp-datetime/fromisoformat-fastpath` experiment.

Contents:

- `fromisoformat_usage_scan.py`: scans stdlib and a sample third-party
  environment for direct `date/time/datetime.fromisoformat(...)` calls.
- `fromisoformat_bench.py`: benchmark harness for direct parser loops and
  representative third-party call sites.
- `*.json`: raw usage-scan and benchmark output.

The third-party sample environment used by the experiment lives outside the
repository at `/tmp/abc-instancecheck-venv`.
