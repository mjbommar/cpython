# ABC / Protocol `__instancecheck__` — experiment diary

Branch: `exp-abc/instancecheck-cache`, off `main` at `cecf564073f`.

## Goal

Evaluate whether ABC and runtime protocol instance checks can be made
cheaper without breaking compatibility for:

- normal cached ABC hits and misses
- proxy objects that expose a fake `__class__`
- runtime-checkable protocols satisfied by instance attributes
- dynamic mutation of classes participating in protocol checks

## Process

1. Inventory stdlib tests and a third-party sample that rely on ABC and
   runtime protocol instance checks.
2. Define a small set of candidate `_abc` / `typing` refactors.
3. Benchmark each variant against synthetic loops and representative
   stdlib / third-party call sites.
4. Validate semantics for tricky compatibility cases.
5. Feed the recommendation back into `Misc/cpython-perf-ideas.md`.

## Candidate refactors

- **Baseline** — current `_abc._abc_instancecheck()` plus
  `_ProtocolMeta.__instancecheck__`.
- **C subtype positive-cache fast path** — check `Py_TYPE(instance)`
  against `_abc_cache` before fetching `instance.__class__`.
- **C exact-type fast path** — skip `instance.__class__` entirely when
  the instance type appears to use the default `__class__` lookup.
- **Protocol type-result cache** — cache structural protocol positives
  by `(protocol_cls, type(instance))`.

## Ecosystem inventory findings

`abc_instancecheck_usage_scan.py` found relevant ABC / runtime-protocol
traffic in:

- stdlib sources: 40 files under `Lib/`
- stdlib tests: 15 files under `Lib/test/`
- tools: 1 file under `Tools/`
- third-party sample: 167 files under the sample `site-packages`

Representative stdlib tests and consumers:

- `Lib/test/test_abc.py`
- `Lib/test/test_typing.py`
- `Lib/test/test_context.py`
- `Lib/test/test_importlib/metadata/_path.py`
- `Lib/test/test_importlib/resources/_path.py`
- `Lib/inspect.py`

Representative third-party consumers from the sample environment:

- `anyio/functools.py`
- `httpx/_models.py`
- `httpx/_content.py`
- `jsonschema/_utils.py`
- `jsonschema/protocols.py`
- `jsonschema/validators.py`
- `typeguard/_checkers.py`
- `pydantic/_internal/_core_utils.py`
- `pydantic/_internal/_utils.py`

The installed sample with the strongest heuristic signal included
`beartype`, `jsonschema`, `pydantic`, `pandera`, `typeguard`,
`httpx`, `anyio`, `fastapi`, and `starlette`.

The raw inventory is stored in
`Misc/abc-instancecheck-perf-data/usage-scan.json`.

## Benchmark corpus

Baseline interpreter: `/tmp/cpython-main-bench/python` from `main` at
`cecf564073f`.

Third-party sample environment:
`/tmp/abc-instancecheck-venv/lib/python3.14/site-packages`

Workloads:

- `M1_mapping_positive_cache`: repeated positive ABC hit
- `M2_mapping_negative_cache`: repeated negative ABC miss
- `M3_proxy_fake_class_positive`: proxy object with fake `__class__`
- `M4_protocol_class_method_positive`: method-only runtime protocol
- `M5_protocol_instance_attr_positive`: runtime protocol satisfied by
  instance attributes
- `M6_protocol_negative`: failing runtime protocol check
- `R1_inspect_isawaitable`: stdlib `inspect.isawaitable`
- `R2_httpx_encode_request_data`: `httpx._content.encode_request(data=...)`
- `R3_httpx_encode_request_content_iterable`:
  `httpx._content.encode_request(content=<iterable>)`
- `R4_typeguard_check_type`: `typeguard._checkers.check_mapping`
- `R5_jsonschema_equal`: `jsonschema._utils.equal`
- `R6_jsonschema_validator_protocol`:
  `isinstance(..., jsonschema.protocols.Validator)`

## Variant results

`baseline`, `c-fast`, and `c-exact` were each run twice and averaged.
`protocol-cache` was run once because it was immediately suspect from a
compatibility perspective.

### Averaged C-variant comparison

| Workload | baseline | `c-fast` | `c-exact` |
| --- | ---: | ---: | ---: |
| `M1_mapping_positive_cache` | 84.619 ms | 73.674 (`-12.9%`) | 71.508 (`-15.5%`) |
| `M2_mapping_negative_cache` | 90.338 | 101.656 (`+12.5%`) | 99.480 (`+10.1%`) |
| `M3_proxy_fake_class_positive` | 24.655 | 26.749 (`+8.5%`) | 28.138 (`+14.1%`) |
| `M4_protocol_class_method_positive` | 56.919 | 53.633 (`-5.8%`) | 52.150 (`-8.4%`) |
| `M5_protocol_instance_attr_positive` | 406.102 | 402.749 (`-0.8%`) | 404.883 (`-0.3%`) |
| `M6_protocol_negative` | 486.220 | 486.745 (`+0.1%`) | 483.079 (`-0.6%`) |
| `R1_inspect_isawaitable` | 87.330 | 80.591 (`-7.7%`) | 81.275 (`-6.9%`) |
| `R2_httpx_encode_request_data` | 438.384 | 429.306 (`-2.1%`) | 431.407 (`-1.6%`) |
| `R3_httpx_encode_request_content_iterable` | 153.874 | 151.675 (`-1.4%`) | 154.212 (`+0.2%`) |
| `R4_typeguard_check_type` | 780.254 | 766.618 (`-1.8%`) | 775.604 (`-0.6%`) |
| `R5_jsonschema_equal` | 356.616 | 339.767 (`-4.7%`) | 341.900 (`-4.1%`) |
| `R6_jsonschema_validator_protocol` | 38.247 | 34.966 (`-8.6%`) | 35.391 (`-7.5%`) |

Observations:

- `c-exact` wins harder on the pure positive-hit microbenchmarks.
- `c-fast` wins more often on the representative real workloads.
- Both C variants make negative-cache and fake-`__class__` micros
  slower, but `c-fast` keeps that penalty smaller.

### `typing` protocol-cache prototype

The experimental `typing.py` cache was measured once on top of the
`c-exact` build.

Notable single-run results versus baseline:

- `M4_protocol_class_method_positive`: `+95.3%`
- `M5_protocol_instance_attr_positive`: `-77.6%`
- `M6_protocol_negative`: `+12.9%`
- `R6_jsonschema_validator_protocol`: `+94.2%`

That prototype was too unstable and too mixed to justify further work.

## Semantic compatibility findings

`c-fast` preserves the important proxy behavior. Both of these still
match baseline semantics on the branch:

- `@property def __class__(self): return dict`
- `def __getattribute__(self, "__class__"): return dict`

The branch now includes
`test_abc.TestABC.test_instancecheck_respects_dynamic___class__`
to keep that behavior pinned.

The `typing` protocol-cache prototype is not shippable as designed.
After the ABC invalidation token stabilizes, it can incorrectly reuse a
successful check for later instances of the same type that do **not**
satisfy the protocol via instance attributes:

- baseline: `MaybeX(True)` -> `True`, later `MaybeX(False)` -> `False`
- cached prototype: once the type entry is populated, later
  `MaybeX(False)` -> `True`

It also made some protocol-heavy workloads substantially slower.

## Chosen patch

The branch keeps only the conservative `_abc.c` change:

- check `Py_TYPE(instance)` against `_abc_cache` before fetching
  `instance.__class__`
- leave `typing.py` unchanged
- add a regression test for dynamic `__class__` proxies

This is smaller than the original two-part idea, but it is the best
version supported by the measurements.

## Validation

On the final branch state:

- `test_abc`: passed
- `test_typing`: passed
- `test_inspect`: passed
- `test_context`: passed
- `test_collections`: passed
- `test_pathlib`: passed

These were run together under:

`./python -m test -j4 test_abc test_typing test_inspect test_context test_collections test_pathlib`

## Recommendation

1. **Ship the `_abc.c` subtype positive-cache fast path**. It is tiny,
   preserves behavior, and delivers consistent wins on representative
   workloads.
2. **Do not ship the `typing.py` protocol type cache**. It is both
   semantically unsafe and performance-unstable.
3. **Drop the more aggressive `c-exact` path for now**. It is still
   interesting, but the extra complexity did not beat the simpler
   `c-fast` variant on the averaged real workloads.

## Raw data

Saved in `Misc/abc-instancecheck-perf-data/`:

- `usage-scan.json`
- `baseline.json`
- `baseline-run2.json`
- `c-subtype-positive-cache.json`
- `c-subtype-positive-cache-run2.json`
- `c-default-class-fastpath.json`
- `c-default-class-fastpath-run2.json`
- `c-default-plus-protocol-type-cache.json`
