# CPython `json` perf campaign — experiment diary

Branch `exp-json/research` off `main` at `2faceeec5c0`. Roadmap:
`Misc/json-perf-roadmap.md`. Raw agent analyses:
`Misc/json-perf-data/research/`. Raw bench data:
`Misc/json-perf-data/*.json`.

Ten experiments evaluated; eight shipped; one rejected; one skipped
because the underlying assumption was wrong.

## Result summary (vs main, 21-run trimmed mean, taskset-pinned)

| scenario                   | main    | final    | delta   |
|----------------------------|--------:|---------:|--------:|
| J1 web-api dumps           |  6.36 µs|  5.52 µs | **−13.2%** |
| J2 log-line dumps          |  2.09 µs|  1.76 µs | **−15.8%** |
| J3 ndjson loads            |  1.65 µs|  1.51 µs |  **−8.6%** |
| J4 bulk dump 100k records  | 80.6 ms | 69.0 ms  | **−14.4%** |
| J5a unicode `ensure_ascii=T` | 2128 µs | 2000 µs | −6.1% |
| J5b unicode `ensure_ascii=F` | 1421 µs | 1214 µs | **−14.6%** |
| J6 numeric-heavy           | 27.5 ms | 25.2 ms  | −8.5% |
| J7 config loads (cold)     | 249.5 µs|  248.5 µs| −0.4% |
| J8 deep tree roundtrip     | 3492 µs | 3047 µs  | **−12.7%** |

Encoder-heavy scenarios benefit most (−13% to −16% on J1/J2/J4/J5b/J8).
J7 config-loads basically unchanged — decoder string scanner was not
moved after E2 turned out to be a regression. J5a (`ensure_ascii=True`
with heavy Unicode) moved less than J5b because the 1-byte fast path
in E1 doesn't fire on 2-byte-kind strings.

## Per-experiment breakdown

Cumulative delta vs main after each ship; individual add'l is the
difference between consecutive columns.

|          | E3   | E5   | E1   | E9   | E10  | E11  | E7   | E14  |
|----------|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|
| J1       | −1.9 | −3.7 | −5.0 | −4.3 | −7.3 | −8.9 |−11.9 |−13.2 |
| J2       | −1.0 | −1.4 | −3.2 | −3.2 | −6.5 |−13.9 |−16.5 |−15.8 |
| J3       | +0.7 | −0.5 | −0.8 | −8.6 | −9.7 | −7.9 | −7.7 | −8.6 |
| J4       | −1.2 | −2.8 | −4.7 | −4.5 |−12.1 |−11.9 |−14.3 |−14.4 |
| J5b      | −3.5 | −5.7 | −7.1 | −5.2 |−14.9 |−12.5 |−13.8 |−14.6 |
| J6       | −0.4 | −2.0 | −0.3 | −0.6 | −3.2 | −2.2 | −8.7 | −8.5 |
| J8       | −0.4 | −2.0 | −3.6 | −8.2 |−14.1 |−13.2 |−13.2 |−12.7 |

### Shipped

**E3 — exact-type dispatch reorder in `encoder_listencode_obj`.**
Lift `Py_TYPE(obj)` once; identity-check against the six exact
builtin types (`PyUnicode/Dict/List/Long/Float/Tuple`) before the
subclass-aware fallback chain. Bool/None/True/False identity checks
kept AFTER the exact-int check and BEFORE the generic int fallback —
bool is a subclass of int so reordering naïvely would encode True
as "1". **−1.9% J1, −3.5% J5b.** Pattern P3/P4.

**E5 — raw `PyObject**` accumulator in `_parse_array_unicode`.**
Per-element `PyList_Append` replaced by `PyMem_Realloc`-backed
growable array; final `PyList_New(n) + PyList_SET_ITEM` bulk.
**−3.7% J1, −5.7% J5b.** Pattern P1 (marshal Exp 1).

**E1 — single-pass classifier scan for 1-byte-kind strings.**
Two 256-entry byte tables (`_ascii_escape_tbl`, `_escape_tbl`); for
`kind == PyUnicode_1BYTE_KIND` a single pass replaces the
two-pass size+emit of `ascii_escape_size`/`escape_size`. No-escape
strings skip allocation entirely. Stops short of full SWAR — the
compiler's auto-vectorization of the byte loop is good enough.
**+1.3pp J1, +1.4pp J5b.**

**E9 — small-int fast path in `_match_number_unicode`.**
For non-float literals ≤18 decimal digits (int64 safe), parse inline
into a `long long` and call `PyLong_FromLongLong`, skipping the
`PyBytes_FromStringAndSize` + `PyLong_FromString` round-trip. Falls
back cleanly for bignums. **+7.8pp J3, +4.6pp J8.** Pattern P4/P5.

**E10 — cached ASCII separator buffers on the Encoder.**
If `item_separator`/`key_separator` are ASCII at `encoder_new`, cache
raw `char*` + length on the Encoder object. Hot path swaps
`PyUnicodeWriter_WriteStr` for `PyUnicodeWriter_WriteASCII`.
**+7.6pp J4, +9.7pp J5b, +5.9pp J8.** Pattern P5/P10 — the single
biggest win of the campaign.

**E11 — writer size hint at encode entry.**
`PyUnicodeWriter_Create(size_hint)` using
`PyDict_GET_SIZE(obj)*24` / `PyList_GET_SIZE(obj)*8` as a crude
lower bound. Avoids the first 2-3 writer reallocations.
**+7.4pp J2.**

**E7 — direct `PyOS_double_to_string` to writer for finite floats.**
`encoder_write_float_direct` uses `PyOS_double_to_string + WriteASCII`
and `PyMem_Free`, skipping the `PyFloat_Type.tp_repr` temp PyUnicode.
Non-finite floats still take the `encoder_encode_float` path.
**+6.5pp J6 numeric-heavy, +3.0pp J1, +2.6pp J2.**

**E14 — extend cached ASCII separator to list/tuple encode.**
`_encoder_iterate_fast_seq_lock_held` was still using `WriteStr` for
the between-element separator. Hoist the E10 check to loop-prologue
locals.  **+1.3pp J1, +0.8pp J5b.**

### Rejected

**E2 — kind-specialised decoder string scan.**
Hoisted the `kind` dispatch out of `scanstring_unicode`'s inner loop
into a flat `ucs1` scanner using raw `const uint8_t *`. Under
contamination the delta looked huge (+40%+), but even on a quiet
machine E2 was +1-2pp regression vs E3+E5+E1+E9 on J3 (−7.0% vs
−8.6%). The compiler already auto-vectorises the `PyUnicode_READ`
macro well; the manual specialisation adds an extra branch that
perturbs the hot path. **Reverted.** Anti-pattern A2 (don't
re-specialise what the compiler already handles).

### Skipped

**E4 — module-level decoder key-memo cache.**
The roadmap assumed each `json.loads(s)` constructs a fresh
`JSONDecoder`, so per-instance `self.memo = {}` would miss shared
keys across calls. In fact `Lib/json/__init__.py:244` already
instantiates a module-level `_default_decoder = JSONDecoder()`, so
the memo is already effectively module-scoped for the common case.
Skipping avoids duplicating an existing optimisation.

### Not attempted

- **E6 — partial-eval Encoder config.** Too complex relative to the
  already-captured wins; the easy parts (cache separators, size hint)
  already landed as E10/E11. Remaining gain mostly on the `markers`
  dict, already handled by E8 candidate.
- **E8 — stack-allocated marker set.** Complex rewrite for a
  predicted 2-4% win. Defer — not worth the code complexity after
  the above landed 12-16% on the same scenarios.
- **E12 — `_PyDict_NewPresized(8)` for decode objects.** Starting
  cap is already 8; no-op.
- **E13 — skip Py_NewRef/DECREF for exact-str dict keys.** Marginal
  (~2-5 ns per key). Not measured.

## Methodology notes

**Contamination is real.** One run was poisoned by a concurrent
`make -j24 bzImage` from a parallel Claude session sharing CPU 0;
every scenario showed +40 to +100% deltas. Caught via a paired
re-bench (revert E2, measure both configs back-to-back under the
same load). Lesson carried from marshal/pickle/logging campaigns
(Anti-pattern A6). Raw data kept for both runs — only the clean
set informs the decision.

**Guardrails as a gate.** `Misc/json-perf-data/guardrails.py` runs
25 correctness checks before every bench. Covers the agent-S golden
rule: exact-type fast paths only when `Py_TYPE(obj) == &PyFoo_Type`,
bool-before-int, IntEnum-as-int, `str` subclass, `list` subclass
`__iter__`, `dict` subclass `items()`, signed zero, big int, circular
reference, `object_pairs_hook`, lone surrogates, control char
escaping, `allow_nan` on/off, surrogate-pair encoding, `default`
hook, `sort_keys` coercion, insertion order, `parse_float=Decimal`,
and trailing-comma/unquoted-key rejection.

**`test_json` regression.** 226 tests run on every commit. All pass.

## 2026-04-18 deeper follow-up

The original campaign stopped after `test_json` plus the stdlib
realistic bench. This follow-up widened the evidence base in two ways:

- broader third-party compatibility and performance coverage
- two additional `_json.c` ideas tested after the first campaign and
  rejected

`Misc/json-perf-data/json_third_party_bench.py` and
`Misc/json-perf-data/README.md` were added so the wrapper/framework
reruns are reproducible.

### Broader package ecosystem coverage

Imports succeeded on both rebuilt `main` and the rebuilt branch for:

- `starlette`
- `fastapi`
- `httpx`
- `dataclasses_json`
- `jsonschema`
- `flask`
- `django`
- `structlog`
- `uvicorn`
- `gunicorn`
- `celery`
- `simplejson`
- `orjson`
- `ujson`

The deterministic smoke outputs matched `main` byte-for-byte for the
stdlib-`json` call paths exercised through:

- `httpx.Request(..., json=payload)`
- `httpx.Response(...).json()`
- `starlette.responses.JSONResponse`
- `fastapi.responses.JSONResponse(jsonable_encoder(...))`
- `Flask.app.json.dumps`
- `django.http.JsonResponse`
- `dataclasses_json` `to_json()` / `from_json()`
- `jsonschema.validate(json.loads(...), schema)`

### Package-backed JSON bench (vs rebuilt `main`)

All results below are trimmed-mean microseconds per operation:

| scenario | `main` | branch | delta |
| --- | ---: | ---: | ---: |
| `httpx_request_json` | 19.33 µs | 18.67 µs | **−3.4%** |
| `httpx_response_json` | 10.48 | 10.14 | **−3.2%** |
| `starlette_jsonresponse` | 3.06 | 2.66 | **−13.1%** |
| `fastapi_jsonresponse` | 8.88 | 8.48 | **−4.5%** |
| `flask_json_dumps` | 3.17 | 2.69 | **−15.1%** |
| `django_jsonresponse` | 6.43 | 5.99 | **−6.8%** |
| `dataclasses_json_to` | 16.55 | 15.62 | **−5.6%** |
| `dataclasses_json_from` | 42.98 | 41.43 | **−3.6%** |

The third-party read is therefore consistent with the stdlib realistic
bench: the branch is not just winning on isolated micros, it is still
ahead once wrapped in common web/framework helpers.

### Additional ideas tested after the first campaign

Two smaller follow-up ideas were tried and rejected:

- exact-`str` key refcount elision inside `encoder_encode_key_value`
- an exact-dict `sort_keys=True` path using `PyDict_Items(...)`
  instead of `PyMapping_Items(...)`

Both patches kept `test_json` green and preserved the third-party smoke
outputs, but both regressed the core realistic bench:

| idea | `J1` | `J2` | `J3` | `J4` | `J8` |
| --- | ---: | ---: | ---: | ---: | ---: |
| exact-`str` key ref elision | +3.6% | +4.0% | +3.4% | +2.2% | +5.8% |
| exact-dict `sort_keys` path | +5.8% | +4.0% | +4.5% | +3.4% | +6.4% |

Those follow-up patches were reverted.

### Updated recommendation

The branch is now stronger than the original diary suggested. It has:

- the original realistic-bench wins
- byte-identical smoke coverage on modern wrapper/framework paths
- package-backed speedups on `httpx`, `starlette`, `fastapi`,
  `flask`, `django`, and `dataclasses_json`

Updated recommendation: promote `exp-json/research` from "strong
research branch" to "ready to split into filing candidates", with an
encoder-first sequence:

1. `E3 + E10 + E11 + E14`
2. `E1`
3. `E5 + E9`

## What shipped

Eight C-side optimisations in `Modules/_json.c` (~150 lines added).
Zero Python changes to `json` itself.  New benchmark/README files only.
No new module state. No
change to the exposed C API or to the documented Python API.

## Sequencing for a PR

1. **E3 alone** — safest (no behavioural change, minimal diff).
2. **E3 + E10 + E11** — the encoder-config-cache bundle. Highest
   leverage. −8 to −12% on common encoders.
3. **E3 + E5 + E9** — decoder bundle. Array fast-accumulator + small
   int parse. −8 to −9% on decoder-heavy.
4. **E3 + everything** — full campaign, −13 to −16% on hot paths.

PR 1+2 is the conservative ask; PR 3 requires an additional reviewer
willing to look at the number-parse fast path.
