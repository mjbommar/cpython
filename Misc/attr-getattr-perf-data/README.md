# Generic `getattr` / Dict-Lookup Experiment

Reusable artifacts for the `exp-attr/generic-getattr-fastpaths` branch.

This directory is the branch-local record for exploring generic attribute
access and dict/type-lookup fast paths highlighted by the service-workload
profiling pass.

Artifacts:

- `attr_getattr_usage_scan.py`
  - scans stdlib and sample `site-packages` for attribute-heavy patterns such
    as `__getattr__`, `__getattribute__`, `property`, and `getattr(...)`
- `attr_getattr_bench.py`
  - micro + real-workload benchmark corpus for candidate patches
- `attr_getattr_checks.py`
  - focused semantic checks for descriptor precedence, `__getattr__`, and
    custom `__getattribute__` behavior
- generated JSON artifacts
  - `usage-scan.json`
  - `baseline.json`
  - `c*.json` candidate benchmark outputs

Outcome summary:

- The branch ended as a negative-result experiment, not a filing
  candidate.
- The `find_name_in_mro()` own-dict-first tweak (`C2`) looked plausible
  on the benchmark corpus, but failed `test_descr` with an MRO /
  re-entrant-lookup regression.
- The stackref-native generic-`getattr` idea (`C1` and supersets)
  showed attractive micro wins but broke Django import during broader
  compatibility checks.
- The only clearly safe tweak was the exact-dict-only known-hash lookup
  (`C3b`), and it was too close to noise on the real workloads to be
  worth pursuing.

See `Misc/attr-getattr-perf-diary.md` for the full narrative and the
final recommendation.

Typical usage:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/attr-getattr-perf-data/attr_getattr_checks.py

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/attr-getattr-perf-data/attr_getattr_usage_scan.py \
  > Misc/attr-getattr-perf-data/usage-scan.json

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/attr-getattr-perf-data/attr_getattr_bench.py \
  --label baseline --output Misc/attr-getattr-perf-data/baseline.json
```
