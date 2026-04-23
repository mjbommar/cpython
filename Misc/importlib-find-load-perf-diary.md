# importlib `_find_and_load` fast-path diary

Date: `2026-04-22`
Branch: `exp-importlib/find-load-mainline`

## Goal

Reduce overhead on the import fast path identified by the full regrtest
profile:

- `Lib/importlib/_bootstrap.py:_find_and_load_unlocked()`
- `Lib/importlib/_bootstrap.py:_find_and_load()`

## Benchmark Harness

Added `Misc/importlib-find-load-perf-data/find_load_bench.py`.

The panel covers:

- already-loaded builtin module lookup
- already-loaded Python module lookup
- repeated top-level source module imports
- repeated package-child source imports
- top-level missing-module imports
- package-child missing-module imports

The harness uses pyperf via the existing local pyperf installation:

```bash
PYTHONPATH=/home/mjbommar/projects/personal/cpython-stringzilla-fastpaths/venv/cpython3.15-3fda47db6754-compat-31b33d68c68a/lib/python3.15/site-packages \
    ./python Misc/importlib-find-load-perf-data/find_load_bench.py --fast --output /tmp/importlib-find-load-*.json
```

## E1/E2: exact-module loaded fast path

Accepted shape:

- cache the exact module type during `_setup()`, where injected `sys` is
  available
- in `_find_and_load()`, return exact modules immediately when `__spec__`
  is `None` or an exact `ModuleSpec` whose `_initializing` flag is false
- keep the original slow path for custom module objects and custom
  `__spec__` objects, because reading `_initializing` there can execute
  Python and mutate `sys.modules`
- carry the result of `name.rpartition('.')` through
  `_find_and_load_unlocked()` to avoid recomputing the child name

Benchmark result
(`/tmp/importlib-find-load-baseline.json` vs
`/tmp/importlib-find-load-candidate-e2.json`):

- `loaded_builtin`: `249 ns` -> `184 ns`, `1.35x faster`
- `loaded_python`: `244 ns` -> `183 ns`, `1.34x faster`
- reload and missing-module cases: no significant change
- pyperf significant geometric mean: `1.10x faster`

Validation:

- focused: `./python -m test -q test_importlib test_import test_zipimport`
  passed, `1,477` tests, `31` skipped, `9.9 sec`
- full clean-mainline: `./python -m test -q -j8` passed,
  `49,881` tests, `2,624` skipped, `491/502` test files,
  `4 min 15 sec`

## Decision

Accept for the stacked winner.

The win is intentionally narrow but targets one of the hottest regrtest
profile paths: already-loaded imports.  The final shape avoids the unsafe
version that returned after reading arbitrary custom `__spec__` objects.
