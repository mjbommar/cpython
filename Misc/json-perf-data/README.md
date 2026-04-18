# JSON Perf Raw Data

Raw artifacts backing `Misc/json-perf-diary.md`.

## Bench scripts

- `json_realistic_bench.py` — the core campaign harness covering the
  nine realistic stdlib scenarios (`J1` through `J8`, with `J5` split
  by `ensure_ascii`).
- `json_third_party_bench.py` — package-backed workloads that still
  route through stdlib `json`, currently covering `httpx`,
  `starlette`, `fastapi`, `flask`, `django`, and `dataclasses_json`.
- `guardrails.py` — the correctness gate run before every benchmark.
  Covers exact-type fast-path safety, circular detection, surrogate
  handling, `default`, `sort_keys`, `parse_float=Decimal`, and other
  semantics that are easy to accidentally perturb.
- `aggregate.py` — helper used during the original campaign to compare
  the stacked experiment runs.

## JSON files

The `main-run*.json` and `E*-run*.json` files are the raw outputs from
`json_realistic_bench.py` used for the trimmed-mean tables in the diary.

## Example usage

With a CPython build under test plus the necessary third-party packages:

    PYTHONPATH=/tmp/perf-extra-pkgs ./python Misc/json-perf-data/json_realistic_bench.py
    PYTHONPATH=/tmp/perf-extra-pkgs ./python Misc/json-perf-data/json_third_party_bench.py
