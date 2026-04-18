This directory holds benchmark and inventory artifacts for the
`exp-abc/instancecheck-cache` experiment.

Contents:

- `abc_instancecheck_usage_scan.py`: scans stdlib tests and a sample
  third-party environment for ABC / runtime protocol instance-check usage.
- `abc_instancecheck_bench.py`: benchmark harness for synthetic and
  representative real workloads.
- `*.json`: raw benchmark output and usage-scan data.

The third-party sample environment used by the experiment lives outside the
repository at `/tmp/abc-instancecheck-venv`.
