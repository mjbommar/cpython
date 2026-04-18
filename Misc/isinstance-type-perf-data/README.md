# isinstance / Type-Lookup Experiment

Reusable artifacts for the `exp-isinstance/type-lookup` branch.

This directory is the branch-local record for exploring the
`isinstance` / ABC / subtype / type-lookup family highlighted by the
service workload profiling pass.

Artifacts:

- `isinstance_type_usage_scan.py`
  - scans stdlib and sample `site-packages` for ABC / Protocol /
    `isinstance` / `issubclass` usage
- `isinstance_type_bench.py`
  - micro + real-workload benchmark corpus for candidate patches
- `isinstance_type_checks.py`
  - focused semantic checks for dynamic `__class__`, runtime protocols,
    and basic `isinstance` invariants
- generated JSON artifacts
  - `usage-scan.json`
  - `baseline.json`
  - `c*.json` candidate benchmark outputs

Typical usage:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/isinstance-type-perf-data/isinstance_type_checks.py

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/isinstance-type-perf-data/isinstance_type_bench.py \
  --label baseline --output Misc/isinstance-type-perf-data/baseline.json
```

See `Misc/isinstance-type-perf-diary.md` for the candidate comparison and
final recommendation.
