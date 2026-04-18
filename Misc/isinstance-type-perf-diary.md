# `isinstance` / ABC / Type-Lookup Perf Diary

Branch: `exp-isinstance/type-lookup`

## Goal

Follow up on the service-workload profiling pass, which repeatedly put
`object_isinstance`, `_abc._abc_instancecheck`, `PyType_IsSubtype`,
`_PyType_LookupStackRefAndVersion`, and generic MRO lookup on the hot path
for FastAPI-, Django-, Celery-, and `jsonschema`-style workloads.

The objective here was not "rewrite `isinstance`", but to test a small set
of coherent fast-path ideas around:

- `_abc.c` avoiding unnecessary `instance.__class__` work
- `typeobject.c` avoiding obviously redundant subtype / MRO work
- combinations of the two, since they show up in the same call chains

## Inventory

### Usage scan

`Misc/isinstance-type-perf-data/isinstance_type_usage_scan.py` scanned `Lib`,
`Lib/test`, `Tools`, and `/tmp/perf-extra-pkgs`.

High-signal hits included:

- stdlib: `typing`, `inspect`, `tracemalloc`, importlib tests
- third party: `django`, `celery`, `jsonschema`, `pydantic`,
  `typeguard`, `structlog`, `typing_extensions`

That matched the earlier service-profile signal closely enough to justify a
small dedicated branch.

### Benchmark corpus

`Misc/isinstance-type-perf-data/isinstance_type_bench.py` covers:

- micros:
  - positive / negative ABC cache paths
  - fake-`__class__` proxy path
  - runtime protocol positives / negatives
- representative real workloads:
  - `inspect.isawaitable`
  - `httpx` request-data encoding
  - `typeguard` mapping checks
  - `jsonschema._utils.equal`
  - direct `jsonschema.protocols.Validator` checks
  - `jsonschema` validation
  - minimal Django request flow
  - Celery eager task dispatch

`Misc/isinstance-type-perf-data/isinstance_type_checks.py` adds focused
semantic coverage for:

- dynamic `__class__` proxies
- runtime protocols satisfied by class methods and instance attributes
- basic `isinstance` invariants

## Candidate Patterns

I tested eight directions.

1. `C1`: `_abc.c` subtype-cache fast path
   - Check `_abc_cache` with `Py_TYPE(instance)` before fetching
     `instance.__class__`.
2. `C2`: aggressive subtype-first `__subclasscheck__`
   - Try `__subclasscheck__(Py_TYPE(instance))` before `instance.__class__`.
3. `C3`: `PyType_IsSubtype` direct-edge shortcut
   - Fast-return for `a == b`, `a->tp_base == b`, and `b is object`.
4. `C4`: `find_name_in_mro` own-dict-first
   - Probe the type's own dict before taking a strong ref to the full MRO.
5. `C5`: `C1 + C3`
6. `C6`: `C1 + C4`
7. `C7`: `C1 + C3 + C4`
8. `C8`: guarded `_abc` subtype-cache
   - Only trust `Py_TYPE(instance)` when the type still resolves
     `__class__` through the default `object.__class__` descriptor.

## Results

Percent deltas below are versus the rebuilt branch baseline.

### Head-to-head table

| Candidate | Real-workload read | Main issue | Verdict |
|---|---:|---|---|
| `C1` | broad `-1.6%` to `-9.7%` wins, but `jsonschema_validate +1.8%` | fake-`__class__` proxy micro `+71.1%` | too spiky alone |
| `C2` | strong on some hits | roughly doubled negative/proxy micros in the early run | reject |
| `C3` | `httpx -11.9%`, `django -2.9%`, `celery -1.8%` | `jsonschema` protocol path regressed slightly | best low-risk patch |
| `C4` | small mixed wins | too noisy / too small alone | reject alone |
| `C5` | good real wins | `jsonschema_validate +4.5%`, proxy `+70.9%` | reject |
| `C6` | good real wins | proxy `+71.0%` | runner-up |
| `C7` | best aggregate real-workload average | proxy `+70.5%` niche perf regression | recommended branch state |
| `C8` | keeps proxy near-flat | negative ABC miss `+12.5%`, Celery flat/slightly worse | interesting fallback, not winner |

### Key deltas

`C7` (`_abc` subtype-cache + subtype direct edges + own-dict-first MRO):

- `M1_mapping_positive_cache`: `-18.9%`
- `M2_mapping_negative_cache`: `-3.1%`
- `M3_proxy_fake_class_positive`: `+70.5%`
- `R1_inspect_isawaitable`: `-10.3%`
- `R2_httpx_encode_request_data`: `-10.9%`
- `R3_typeguard_check_mapping`: `-4.8%`
- `R4_jsonschema_equal`: `-3.8%`
- `R5_jsonschema_validator_protocol`: `-6.2%`
- `R6_jsonschema_validate`: `-0.6%`
- `R7_django_request`: `-2.4%`
- `R8_celery_eager`: `-2.4%`

`C3` (the safest standalone `typeobject.c` patch):

- `M3_proxy_fake_class_positive`: `-3.9%`
- `R2_httpx_encode_request_data`: `-11.9%`
- `R7_django_request`: `-2.9%`
- `R8_celery_eager`: `-1.8%`
- but `R5_jsonschema_validator_protocol`: `+3.2%`

`C8` (guarded `_abc` subtype-cache):

- `M3_proxy_fake_class_positive`: `+2.2%`
- `M2_mapping_negative_cache`: `+12.5%`
- `R2_httpx_encode_request_data`: `-12.1%`
- `R7_django_request`: `-2.1%`
- `R8_celery_eager`: `+0.1%`

## Recommendation

Keep `C7` on the experiment branch.

Why:

- It is the best aggregate result across the representative workloads that
  motivated the branch in the first place.
- It keeps the patch surface bounded to two coherent files:
  `Modules/_abc.c` and `Objects/typeobject.c`.
- The only meaningful downside I found is a performance regression on the
  fake-`__class__` proxy microbenchmark. That path is niche, and the new
  regression test confirms semantics still hold.

If upstream review rejects the proxy perf tradeoff, `C3` is the fallback.
It is materially smaller, keeps the proxy path healthy, and still wins on
several real workloads.

`C8` is not the answer. The extra guard work mostly pays to preserve a niche
micro, and then gives back too much on the negative ABC path.

## Validation

Final branch state (`C7`) passed:

```bash
./python -m test -j4 \
  test_abc test_typing test_inspect test_context test_collections test_pathlib
```

Result: `6` test files, `2,718` tests run, success.

Focused semantic checks also passed:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/isinstance-type-perf-data/isinstance_type_checks.py
```

Third-party validation passed for the local installable suites we have here:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python -m pytest -q \
  /tmp/perf-extra-pkgs/jsonschema/tests \
  /tmp/perf-extra-pkgs/referencing/tests \
  --ignore=/tmp/perf-extra-pkgs/jsonschema/tests/test_jsonschema_test_suite.py \
  --ignore=/tmp/perf-extra-pkgs/referencing/tests/test_referencing_suite.py
```

Result: `691 passed`.

Notes:

- `jsonschema.tests.test_jsonschema_test_suite` and
  `referencing.tests.test_referencing_suite` require external fixture
  repositories that are not present in this environment.
- `jsonschema.tests.test_exceptions` additionally needed `jsonpath_ng`,
  which was installed into `/tmp/perf-extra-pkgs` for this run.

## Files

- diary: `Misc/isinstance-type-perf-diary.md`
- raw artifacts: `Misc/isinstance-type-perf-data/`
- recommendation candidate on branch: `C7`
