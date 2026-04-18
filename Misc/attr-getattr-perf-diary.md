# Generic `getattr` / Type-Lookup Experiment Diary

Branch: `exp-attr/generic-getattr-fastpaths`

Date: 2026-04-18

## Goal

Follow up on the service-workload profiling pass for Django / Jinja2 /
jsonschema / Celery / FastAPI-ish paths and test whether the hot
`attr + dict + type-lookup` family has a small, safe C-level fast path:

- `Objects/object.c:_PyObject_GetAttrStackRef`
- `Objects/object.c:_PyObject_GenericGetAttrWithDict`
- `Objects/typeobject.c:find_name_in_mro`
- `Objects/dictobject.c` instance/type dict lookup helpers

The branch-local question was not "can we make a microbenchmark go
faster?" but "is there a PR-shaped change that survives descriptor /
MRO semantics and still improves real workloads?"

## Workload inventory

`Misc/attr-getattr-perf-data/attr_getattr_usage_scan.py` scanned stdlib,
tests, tools, and a representative third-party package set.

High-level counts from `usage-scan.json`:

- roots:
  - `Lib`: `675`
  - `Lib/test`: `390`
  - `Tools`: `50`
  - `site-packages`: `909`
- pattern totals:
  - `__getattr__`: `570`
  - `__getattribute__`: `217`
  - `cached_property`: `767`
  - `getattr(...)`: `4041`
  - `hasattr(...)`: `3830`
  - `property`: `2958`
- heaviest sampled third-party users:
  - `django`: `2079`
  - `celery`: `470`
  - `pydantic`: `397`
  - `_pytest`: `365`
  - `kombu`: `258`
  - `werkzeug`: `185`
  - `prompt_toolkit`: `155`
  - `gunicorn`: `127`
  - `typing_extensions.py`: `119`
  - `anyio`: `112`

That confirmed the service-profile signal: the family is broad, but it
is also extremely semantics-sensitive.

## Benchmark corpus

All candidate measurements used:

- focused micros:
  - `M1_instance_attr_hit`
  - `M2_property_hit`
  - `M3_method_lookup_hit`
  - `M4_instance_override_non_data`
  - `M5_missing_hasattr`
  - `M6_slots_hit`
  - `M7_cached_property_hit`
- service-ish workloads:
  - `R1_django_request`
  - `R2_jinja2_render`
  - `R3_jsonschema_validate`
  - `R4_celery_eager`
  - `R5_httpx_request_data`

The reusable harness is
`Misc/attr-getattr-perf-data/attr_getattr_bench.py`.

## Candidate patterns

I tested or partially tested seven concrete shapes:

1. `C1`: stackref-native generic-`getattr` fast path in
   `_PyObject_GetAttrStackRef`
2. `C2`: `find_name_in_mro()` own-dict-first
3. `C3`: broad known-hash instance-dict lookup inside
   `_PyObject_GenericGetAttrWithDict`
4. `C3b`: safer exact-dict-only version of `C3`
5. `C4`: `C1 + C2`
6. `C5`: `C1 + C3` / `C1 + C3b`
7. `C7`: `C2 + C3b`

I did not continue to a `C6 = C1 + C2 + C3*` branch-state once the
stackref family (`C1`, `C4`, `C5`) showed real compatibility failures.

## Results

### `C1` stackref-native generic `getattr`

Initial micro results looked promising:

- `M1_instance_attr_hit`: about `-5.8%`
- `M2_property_hit`: about `-7.6%`
- `M3_method_lookup_hit`: about `-11.5%`

But broader validation rejected it.

Observed failure:

- Django import broke during `models.Field()` construction with:
  - `AttributeError: 'Field' object has no attribute 'remote_field'`

Conclusion:

- This shape is not safe in its current form.
- Even if the direct micro wins are real, the semantics risk is too high
  for a CPython PR candidate.

### `C2` `find_name_in_mro()` own-dict-first

Measured deltas vs baseline:

- `M2_property_hit`: `-6.2%`
- `M3_method_lookup_hit`: `-8.3%`
- `R2_jinja2_render`: `-0.8%`
- `R3_jsonschema_validate`: `-0.6%`
- `R4_celery_eager`: `-0.8%`
- `R5_httpx_request_data`: `-0.7%`
- `R1_django_request`: `+0.4%`

This looked like the least-bad small patch, so I ran the broader test
pass on it.

Validation outcome:

- semantic smoke: passed
- third-party import smoke: passed for `django.forms`, `jinja2`,
  `celery`, `httpx`, `jsonschema`, `flask`, `werkzeug`, `kombu`,
  `pydantic`, `prompt_toolkit`, `gunicorn`
- third-party suites:
  - `jsonschema` + `referencing`: `691 passed`
- stdlib targeted tests:
  - `test_property`, `test_context`, `test_collections`,
    `test_inspect`, `test_functools`, `test_pathlib`: passed
  - `test_descr`: failed

The `test_descr` failure is decisive:

- `test_altmro`: `TypeError: cannot create 'X' instances`
- `test_type_lookup_mro_reference`: subprocess segfault in the
  re-entrant/non-string-key MRO lookup case

Conclusion:

- `C2` is not safe enough.
- The failure mode is exactly in the kind of exotic MRO / dict-reentry
  logic that `find_name_in_mro()` has to preserve.

### `C3` broad known-hash instance-dict lookup

Measured deltas vs baseline:

- `M2_property_hit`: `-5.7%`
- `M3_method_lookup_hit`: `-7.2%`
- `R4_celery_eager`: `-1.5%`
- `R1_django_request`: `+7.2%`
- `R3_jsonschema_validate`: `+1.3%`
- `R5_httpx_request_data`: `+1.1%`

Conclusion:

- Broad cast-based known-hash lookup is a bad direction.
- It regressed the real Django/httpx/jsonschema paths enough that I did
  not keep pursuing it.

### `C3b` exact-dict-only known-hash lookup

This was the safer rewrite of `C3`.

Measured deltas vs baseline:

- `M2_property_hit`: `-5.2%`
- `M3_method_lookup_hit`: `-6.1%`
- `R1_django_request`: `-0.0%`
- `R2_jinja2_render`: `-0.1%`
- `R4_celery_eager`: `-0.7%`
- `R3_jsonschema_validate`: `+0.5%`
- `R5_httpx_request_data`: `+1.5%`

Validation:

- semantic smoke: passed
- Django import smoke: passed

Conclusion:

- This is the only clearly safe family member I found.
- It is also basically noise on the representative real workloads.
- Not worth a PR.

### `C4` / `C5` stackref combinations

These started from the same stackref-native generic-`getattr` idea as
`C1`.

Observed outcome:

- `C4` benchmarked, but the broader validation later showed that the
  stackref family itself is not trustworthy.
- `C5` failed immediately at Django import with the same
  `Field.remote_field` regression.

Conclusion:

- Do not pursue the stackref-native generic-`getattr` family without a
  much deeper proof of correctness.

### `C7` `C2 + C3b`

Measured deltas vs baseline:

- `M2_property_hit`: `-6.0%`
- `M3_method_lookup_hit`: `-4.3%`
- `M4_instance_override_non_data`: `-2.1%`
- `R1_django_request`: `-0.5%`
- `R3_jsonschema_validate`: `-3.1%`
- `R4_celery_eager`: `-0.4%`
- `R2_jinja2_render`: `+1.7%`
- `R5_httpx_request_data`: `+1.4%`

Validation:

- semantic smoke: passed
- Django import smoke: passed

Conclusion:

- Still too mixed to justify the extra complexity.
- Since `C2` itself failed `test_descr`, this combination is not a
  candidate either.

## Final assessment

This branch is a **negative result** in the useful sense:

- the attr/dict/type-lookup family is definitely hot under service-ish
  workloads
- the obvious C-level fast paths are already close to the correctness
  boundary
- the best-looking changes either:
  - broke descriptor / MRO semantics (`C1`, `C2`, stackref combos), or
  - were too small / noisy to justify themselves (`C3b`)

### Recommendation

Do **not** file a PR from this branch.

Long-term direction, if this family is revisited:

- work through interpreter specialization / `LOAD_ATTR` shape-aware
  paths instead of hand-duplicating generic-`getattr` logic in
  `_PyObject_GetAttrStackRef`
- treat `find_name_in_mro()` as a high-risk area because re-entrant
  dict lookup and non-string-key edge cases are load-bearing
- prefer narrower, already-validated targets like
  `isinstance` / `_abc.c`, logging, AST `NodeVisitor`, and selected
  module-local C micros (`datetime`, `uuid`) before coming back here

## Artifacts

Branch-local artifacts live in `Misc/attr-getattr-perf-data/`:

- `attr_getattr_usage_scan.py`
- `attr_getattr_bench.py`
- `attr_getattr_checks.py`
- `usage-scan.json`
- `baseline.json`
- candidate result files:
  - `c1_stackref_generic_getattr.json`
  - `c2_mro_own_dict_first.json`
  - `c3_known_hash_dict_lookup.json`
  - `c3b_exact_dict_known_hash.json`
  - `c4_stackref_plus_mro_own_dict.json`
  - `c7_mro_own_dict_plus_exact_dict_known_hash.json`
