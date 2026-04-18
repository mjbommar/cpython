# Agent D — Realistic JSON Workload Design for CPython `json` Optimization

## Task 1 — Realistic JSON Workload Scenarios

Ten scenarios, each specified concretely (shape, size, cadence, expected C touchpoint in `Modules/_json.c`). Entry points that matter: `encoder_listencode_obj` / `_dict` / `_list` (line 1569–1916), `encoder_encode_float` (1510), `_encoded_const` (1491), `scan_once_unicode` (1099), `scanstring_unicode` (471), and `py_encode_basestring_ascii_impl` (683).

**S1. Web API response — hot path (`dumps`).**
Dict of 10–14 keys: `{"id": uuid4-str, "ts": iso8601-str, "user_id": int, "ok": bool, "latency_ms": float, "tags": [3–5 short ascii strs], "meta": {"region": "...", "version": "..."} , "items": [list of 5–20 dicts w/ 4–6 keys]}`. Payload ~1–4 KB serialized. Loop 50,000 iterations. Exercises `encoder_listencode_dict` → repeated `_encoded_const` for small strings and `encoder_encode_float`, plus ASCII-fast-path `py_encode_basestring_ascii`.

**S2. Web API request parse (`loads`).**
Same shape as S1 but on the decode side. 50,000 iterations. Exercises `scan_once_unicode` dispatch, `JSONObject`/`JSONArray` in `_json.c` (lines 786/906), keys going through `scanstring_unicode` with no escapes.

**S3. Log shipping (`dumps`, structlog-shaped).**
`{"ts": float, "level": "INFO", "logger": "app.http", "msg": "...", "req_id": str, "path": "/v1/...", "status": 200, "latency_ms": float, "extra": {...small...}}`. ~400 B out. 500,000 iterations in the microbench to amortize. Ninety-plus percent of real cost is `_encoded_const` string lookup and the ASCII escape scan; this is the scenario that pays for branch predictability in `py_encode_basestring_ascii_impl`.

**S4. Config load (`loads`, one-shot).**
Read `pyproject`-like / OpenAPI-like 30 KB file, 200 keys, depth 4–6, some long string values (license text). Call once per benchmark iteration, 2,000 iterations total. Dominated by `scanstring_unicode` (the long-string path, 471–640) and `JSONObject` hash/intern. Cold-cache effects matter — it's the only realistic scenario where dict resize in `JSONObject` shows up.

**S5. Data pipeline — uniform records NDJSON (`loads`).**
100,000-line NDJSON, each line an identical-schema dict of 12 keys (mix int / ISO-date-str / float / short str). `for line in f: json.loads(line)`. Throughput-bound; key-intern memo (`s->memo`) and `PyDict_SetDefault_KnownHash` in `JSONObject` dominate because the same keys recur. This is where key-interning optimizations pay off.

**S6. Data pipeline — bulk dump of uniform records (`dumps`).**
`json.dumps(list_of_100k_dicts)` single call. Tests `encoder_listencode_list` over `PySequence_Fast` (line 1923) and the inner per-dict hot loop. Also stresses `PyUnicodeWriter` buffer growth — realloc cadence is its own profile line.

**S7. Deep nested structure (`dumps` and `loads`).**
Genealogy / AST-like tree, depth 400, fanout 2, ~5k total nodes. Triggers `Py_EnterRecursiveCall` paths and the `markers` circular-ref dict in `encoder_listencode_obj`. Small overall bytes (~80 KB) but stack pressure and dict-membership-check per node dominate.

**S8. Unicode-heavy (`dumps`).**
CJK / emoji / RTL product catalog: list of 5,000 dicts whose `title`/`description` values are 60–300 chars of non-ASCII (Japanese + emoji). Forces `py_encode_basestring_impl` (line 698, non-ASCII path with `ensure_ascii=False`) AND separately with `ensure_ascii=True` (default), which hits the `\uXXXX` escape writer inside `py_encode_basestring_ascii_impl`. Two sub-scenarios: S8a `ensure_ascii=True` (the default, slow), S8b `ensure_ascii=False` (common in modern APIs).

**S9. Numeric-heavy (`dumps`).**
Scientific/analytics payload: list of 20,000 records of `{"t": float, "x": float, "y": float, "n": int, "big": bigint-64-digits}`. Exercises `encoder_encode_float` (uses `PyFloat_Repr`/`float.__repr__`) and the `PyLong_Type` path where `_encoded_const` is NOT used; we fall into the `PyObject_Str(long)` branch near line 1596. Bigints are a known slow path.

**S10. Round-trip fidelity / NaN / custom `default=` (`dumps`+`loads`).**
Mixed payload with `Decimal`, `datetime` (via `default=str`), `set` (via `default=list`). Tests the `default` fallback path in `encoder_listencode_obj` (line 1649, `PyObject_CallOneArg(default)` and recursive encode). Realistic for Django/DRF, Pydantic-v1 fallbacks.

### Code sketch — S1 (Web API)

```python
def payload():
    return {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "user_id": random.randrange(10**6, 10**7),
        "ok": True,
        "latency_ms": random.random() * 120,
        "tags": ["web", "v2", "prod"],
        "meta": {"region": "us-east-1", "version": "1.42.0"},
        "items": [
            {"sku": f"SKU-{i:06d}", "qty": i, "price": i * 1.07, "in_stock": i % 3 != 0}
            for i in range(10)
        ],
    }

def bench_s1_dumps(n=50_000, p=payload()):
    dumps = json.dumps
    for _ in range(n):
        dumps(p)  # same object; measures encoder, not object construction
```

### Code sketch — S5 (NDJSON data pipeline, loads)

```python
LINE = json.dumps({"ts": "2026-04-17T10:00:00Z", "user_id": 123456,
                   "event": "click", "path": "/a/b/c", "dur_ms": 12.3,
                   "session": "abc123def", "country": "US", "ok": True,
                   "a": 1, "b": 2, "c": 3, "d": 4})

def bench_s5(n=200_000):
    loads = json.loads
    # NB: same string → benches the scanner with fully-cached interned keys.
    # Run a sibling variant where each line has a unique session id to defeat interning.
    for _ in range(n):
        loads(LINE)
```

### Code sketch — S8a (Unicode `ensure_ascii=True`)

```python
CJK = "日本語テスト絵文字😀🎉🚀中文测试한국어테스트" * 4
records = [{"title": CJK, "desc": CJK + f" #{i}", "id": i} for i in range(5_000)]

def bench_s8a():
    return json.dumps(records)  # default ensure_ascii=True: every char escaped
```

## Task 2 — Profiling Predictions

Rough per-scenario time breakdowns (percent of wall in `dumps`/`loads` process time, not counting Python dispatch):

- **S1 dumps:** 35% `py_encode_basestring_ascii_impl` (every short str), 20% `encoder_listencode_dict` iteration + separator writes, 15% `PyDict_Next`/hash, 10% `encoder_encode_float`, 8% `PyUnicodeWriter_WriteChar`/`WriteStr`, 12% other. *Wins:* SIMD escape scan, small-string fast-path, separator inlining. *Wastes:* number-format tuning.
- **S2 loads:** 30% `scanstring_unicode`, 20% `JSONObject` dict build + intern, 15% `scan_once_unicode` dispatch switch, 10% `PyFloat_FromString` / number parse, 10% whitespace skip, 15% other. *Wins:* SIMD string scanner (no-escape fast path), key interning cache, whitespace-skip vectorization. *Wastes:* float parsing.
- **S3 dumps:** 55% ASCII escape scan, 15% dict iteration, 10% float format. *Wins:* escape scan SIMD, pre-compiled "no escapes needed" fast path. (This scenario alone justifies escape-scan work.)
- **S4 loads:** 50% `scanstring_unicode` (long strings), 20% dict build, 15% scanner dispatch. Dominated by memcpy of escape-free slices.
- **S5 loads:** 35% `scanstring_unicode` on repeated keys, 25% dict building, 20% number parse. Key-memo hit rate ~99%. *Wins:* promote the memo to `PyUnicode_InternInPlace` once, then pointer-compare.
- **S6 dumps:** 25% `encoder_listencode_dict` inner loop × 100k, 20% ASCII escape, 15% `PyUnicodeWriter` buffer realloc. *Wins:* presize writer from estimate (items × avg_bytes).
- **S7 both:** 25% recursion overhead (`Py_EnterRecursiveCall`, markers dict lookup/insert), 20% per-node construction, rest scattered.
- **S8a dumps:** ~70% in the `\uXXXX` encoder loop (code point to 6-byte hex). *Wins:* batched hex-digit table, dedicated UTF-16 surrogate-pair writer. This is the one scenario where `ensure_ascii` path changes are high-leverage.
- **S8b dumps:** ~45% `py_encode_basestring_impl` scanning for `"` / `\` / control chars in UCS-2/UCS-4 strings. *Wins:* kind-specialized scanners.
- **S9 dumps:** 55% `encoder_encode_float` (calls `float.__repr__` → `PyOS_double_to_string`), 20% bigint `str(long)`. *Wins:* inline float repr, special-case small int `_encoded_const` extended to a cached range. *Wastes:* string escape work.
- **S10:** cost is 50% user `default` callback + Python dispatch; optimizing C is mostly wasted. Useful only to confirm we don't regress.

## Task 3 — Corpus Pointers (use real data, don't synthesize)

- **GitHub Archive** — hourly gzipped NDJSON of public GH events. URL pattern `https://data.gharchive.org/2024-01-15-12.json.gz`. ~40–120 MB/hour, dicts of 8–15 keys, nested `payload`, ASCII-heavy. Perfect for S5, S6.
- **HuggingFace datasets — `allenai/c4` or `HuggingFaceFW/fineweb`** — snapshots are JSONL, multilingual. Use for S8. `https://huggingface.co/datasets/allenai/c4`.
- **npm registry metadata** — `https://replicate.npmjs.com/_all_docs?include_docs=true` or per-package `https://registry.npmjs.org/<pkg>`. Deeply nested, big `dependencies` dicts. Good for S4/S7.
- **PyPI JSON API** — `https://pypi.org/pypi/<pkg>/json`. ~50–300 KB per package, realistic config-style payload for S4.
- **CloudWatch / AWS sample logs** — the AWS `aws-samples/amazon-cloudwatch-logs-subscriptions-python` repo has representative log events; also `https://docs.aws.amazon.com/lambda/latest/dg/services-cloudwatchlogs.html` shows the envelope shape. For S3 synthesize structlog-shape from that template.
- **OpenAPI specs** — Kubernetes `api/openapi-spec/swagger.json` on the `kubernetes/kubernetes` GitHub repo, and Stripe's `https://github.com/stripe/openapi`. ~4 MB, deep, many schemas. Ideal S4/S7.
- **Twitter/X sample stream archives on archive.org** (`https://archive.org/details/twitterstream`) — Unicode-heavy JSONL, perfect for S8.
- **Elastic/Kibana bulk API sample** — the Elastic `kibana_sample_data_ecommerce` / `_flights` NDJSON files under `kibana/src/plugins/home/server/services/sample_data/data_sets/`. Uniform schema, great S5.

## Task 4 — Measurement Methodology

Gotchas carried over from the logging bench, adapted for `json`:

1. **Trimmed mean + hi/lo trim**: run N=30 iterations per scenario, drop top-2/bottom-2, report mean + stdev. A single GC pause during encoding a 100k list (S6) skews means badly.
2. **CPU pinning**: `taskset -c 2 python bench.py` on an isolated core; disable turbo/CPPC if the host allows (`cpupower frequency-set -g performance`). JSON benches are nanosecond-sensitive; a P-state transition mid-run is worth tens of percent.
3. **Warmup**: one throwaway run of each scenario before timing; it pre-faults heap, warms the method cache on `PyUnicode_FromObject` etc., and triggers first-time imports.
4. **`gc.disable()` around the timed region** for S6/S7 only (large allocations). Leave GC on for S1/S3 — that's the realistic state.
5. **String-intern side effects between scenarios**: `json.loads` caches keys indirectly via `PyDict_SetDefault_KnownHash` behavior and via `str` interning when keys look like identifiers. Running S2 then S5 will make S5 falsely fast. Mitigation: run each scenario in a fresh `subprocess.run([sys.executable, ...])`, or at minimum call `sys.intern` audit and force-delete common key strings between scenarios. Do NOT run multiple scenarios in one process without isolation.
6. **Small-int cache (`_PyLong_SMALL_INTS`)**: integer values in [-5, 256] never allocate. If benchmarks use `range(256)` as values, you understate bigint/long cost. Ensure numeric scenarios include values outside the cache (e.g., `10**6 + i`).
7. **Float cache / repr**: Python does NOT cache float repr, but CPU float-to-string tables warm the dcache. First timed call after module import can be 20% slow — thus the warmup.
8. **`perf record -F 999` / `py-spy dump`** on a dedicated long run (n=5_000_000 for S3) to collect flat + call-graph. `perf stat -e cycles,instructions,cache-misses,branch-misses` is where the escape-scan wins will show up as branch-miss reductions.
9. **Report dumps/s, MB/s, and ns/op**. `dumps/s` scales by payload, so always also report serialized bytes/s — that's what an SRE actually cares about.
10. **Anti-benchmark-gaming rule**: never reuse the same `dict` object across all iterations of a dumps bench without also running a "fresh-per-iter" variant. PGO/BOLT can specialize on the exact dict layout; real production builds fresh dicts every request.
11. **Ensure both `ensure_ascii` settings are reported separately** — they're effectively two different encoders (entry at line 1580 dispatches on `s->encoding`-style flags); mixing them under one headline number is how regressions hide.
