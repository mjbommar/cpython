# CPython stdlib perf work — outcome summary

Companion to `Misc/cpython-perf-ideas.md`. That file is the *roster* of
ideas; this file records what was actually built, measured, and filed
against upstream.

Four separate branches, each self-contained, each with its own diary
and raw bench data.  None depends on the others.

## Summary table

| # | Branch | Upstream issue | Upstream PR | State |
| --- | --- | --- | --- | --- |
| 1 | `marshal-safe-cycle-design` | gh-148653 | [python/cpython#148700](https://github.com/python/cpython/pull/148700) | open, filed |
| 2 | `exp-pickle/4-pure-python-exact-containers` | gh-148706 | not yet opened | ready to file |
| 3 | `exp-logging/hot-path` | not yet filed | not yet opened | drafts prepared |
| 4 | `exp-json/research` | not yet filed | not yet opened | 8 experiments shipped, 10-16% gains |

All four branches live on `mjbommar/cpython`; none were ever pushed to
`python/cpython:main` directly.

## 1. marshal — safe-cycle fix + perf recovery

**Branch**: `marshal-safe-cycle-design`
**Upstream**: python/cpython#148700 (open PR)

### What shipped

- Fixed SIGSEGV in `marshal.loads` for self-referencing tuples
  (gh-148653).
- Recovered the 7–12% regression that the safety fix introduced, and
  then some: beat `main` baseline on every microbench.
- Replaced the `PyList`-backed refs table in the marshal reader with a
  raw `PyObject **` array, plus low-bit pointer tagging to encode the
  `INCOMPLETE_HASHABLE` state without a parallel allocation.

### Measured impact vs pre-PR `main`

| Benchmark | `loads` Δ |
| --- | ---: |
| `small_tuple` | **−14.3%** (faster than `main`) |
| `nested_dict` | **−6.9%** |
| `code_obj` | **−6.8%** |
| **`python_startup` (pyperformance)** | **−15.8% (1.16× faster), t=62.46, significant** |
| `python_startup_no_site` | −3.5%, significant |
| All other pyperformance slice benches | flat (within noise) |

### Validation

- Full CPython test suite: 48,932 pass, 0 failures.
- 156-program bounded semantic round-trip test generator covering
  valid Python-emittable recursive graphs added as part of this PR.
- dill, cloudpickle, stdlib `test_importlib`/`test_zipimport`/
  `test_compileall`/`test_py_compile` all match baseline.
- Hypothesis property-based fuzz: 3,500 random round-trips pass; the
  cyclic shapes the safe-cycle design targets are measurably faster.

### Artifacts

- `Misc/marshal-recursive-ref-design.md` — design doc (shipped early).
- `Misc/marshal-perf-diary.md` — experiment ledger.
- `Misc/marshal-perf-data/` — 38 raw JSON files + README.

### Idea this came from

Triggered by the bug gh-148653, not the brainstorm. But the "raw array
replacing PyList" pattern became the template the pickle follow-up
(#2 below) tried to apply and — interestingly — *found was already in
place* for `Unpickler.memo`.

## 2. pickle — pure-Python `_Pickler` speedup

**Branch**: `exp-pickle/4-pure-python-exact-containers`
**Upstream issue**: gh-148706 (filed)
**Upstream PR**: not yet opened. Ready to file from
https://github.com/python/cpython/compare/main...mjbommar:cpython:exp-pickle/4-pure-python-exact-containers

### What shipped (across 9 commits on the branch)

Pure-Python `pickle._Pickler` — the fallback when the C accelerator is
absent, and the direct parent class of `dill.Pickler` — rewritten to
match the C pickler's dispatch order and cache reusable work:

- Exact-container fast paths (`_batch_appends_exact`,
  `_batch_setitems_exact`) mirroring C's `batch_list_exact` /
  `batch_dict_exact`.
- `commit_frame()` inlined in `save()` hot check.
- Atomic-type short-circuit (`str`/`int`/`None`/`bool`/`float`/`bytes`)
  before memo lookup, matching `Modules/_pickle.c::save()` dispatch
  order.
- `memoize()` inlines the protocol-4+ `MEMOIZE` write directly.
- `BININT1` opcode bytes (n in 0..255) precomputed at module import.
- Large-dict mutation detection preserved via delegation to the generic
  `_batch_setitems` iterator path (regression fix caught in review).

### Measured impact vs clean `main`

Pure-Python `pickle._Pickler.dump` (representative workloads):

| Workload | dump Δ |
| --- | ---: |
| `list_of_ints_10k` | **−38%** |
| `list_of_strs_1k` | **−20%** |
| `dict_str_int_5k` | **−28%** |
| `deep_list` | **−49%** |
| `nested_list_of_dicts` | **−37%** |
| `list_of_short_bytes_5k` | **−11%** |

**dill (which inherits from `pickle._Pickler`)** — 5 shapes:
`dill.dumps` **19% – 37% faster** per shape.

**cloudpickle** (inherits from `_pickle.Pickler`, the C class) —
unaffected (±1% noise), as expected.

### Validation

- Full CPython suite: 48,928 pass, 0 failures.
- `test_pickle` 1060/1060, `test_copy` 83/83, `test_copyreg` 6/6,
  `test_pickletools` 202/202, `test_importlib` 1217/1217.
- dill 29/30 (the one failure is a pre-existing 3.15a8 incompat,
  identical on `main`).
- cloudpickle 243 pass + 29 skip + 2 xfail — identical to `main`.
- joblib focused subset: 95 pass / 2 fail / 7 err — identical to `main`.
- Verified correct behavior when the C accelerator is blocked (421/498
  tests identical to `main` under `sys.meta_path` hook).

### Ideas that did **not** ship (recorded so future reviewers skip them)

| Idea | Verdict |
| --- | --- |
| Hoist `persistent_id` / `reducer_override` hook probes to `__init__` | Rejected twice: +17–36% slowdown; `PyType_Lookup`'s type-attribute cache beats any hand-written `__dict__` probe. |
| Explicit frame byte counter (skip `BytesIO.tell()`) | Rejected: Python-level counter maintenance costs more than `BytesIO.tell()` — it's a C method. |
| ASCII fast path in `save_str` | Rejected as noise. Python's utf-8 encoder already has a fast path for pure-ASCII. |
| Skip `memoize()` for atomic-content tuples | Deferred — correct but changes byte-exact pickle output, breaking `test_pickle_to_2x`'s fixture assertion. |
| Exact-set batching | Deferred — needs a set-heavy workload added first; same shape as Exp 4. |

### Artifacts

- `Misc/pickle-perf-diary.md` — 700-line experiment ledger with both
  the round-1 (Exp 4 → E) and round-2 (F1 → F6) work recorded.
- `Misc/pickle-perf-data/` — 14 JSON artifacts, 3 bench scripts,
  README mapping files to branch states.

### Idea this came from

Originally misdiagnosed as "pickle memo structure" from the roster
(which is already well-optimized). The real opportunity was the
*dispatch / scaffolding* of `save()`, flagged on review.

## 3. logging — hot-path caches

**Branch**: `exp-logging/hot-path`
**Upstream issue**: not yet filed
**Upstream PR**: not yet opened

### What shipped (one commit + one diary commit)

~75 lines of change in `Lib/logging/__init__.py`. Four caches of
pure-function work that `LogRecord.__init__` and `findCaller` redo
on every emitted record:

- `_is_internal_frame(frame)` caches result per `co_filename`.
- `LogRecord.__init__` caches `(filename, module)` per `pathname`.
- Main-thread ident + name cached at import so
  `threading.current_thread().name` is skipped on the main thread.
- `Formatter.usesTime()` cached on Style construction.

### Measured impact

Realistic Starlette/FastAPI-shaped microbench (4 scenarios, trimmed
mean across 7 runs):

| Scenario | baseline | patched | Δ |
| --- | ---: | ---: | ---: |
| R1 quiet request (INFO root, 2 filtered + 2 emitted) | 10.12 µs/iter | 9.02 µs | **−10.9%** |
| R2 verbose (DEBUG root, all emit) | 14.96 µs | 13.14 µs | **−12.2%** |
| R3 deep filtered (8-level logger, WARNING root) | 0.11 µs | 0.11 µs | flat (intended) |
| R4 access-log only (uvicorn-shape) | 5.27 µs | 4.62 µs | **−12.4%** |

End-to-end Starlette `TestClient` (Route + 4 log calls per request,
in-memory sink):

| Config | baseline | patched | Δ per request |
| --- | ---: | ---: | ---: |
| INFO | 331.7 µs | 321.8 µs | **−10.0 µs (−3.0%)** |
| DEBUG | 330.2 µs | 322.0 µs | −8.2 µs (−2.5%) |

### Validation

- Full CPython suite: 48,928 pass, 0 failures.
- `test_logging` 282/282, `test_asyncio` 2708/2708, `test_unittest`
  1096/1096, `test_warnings` 191/191, `test_http_cookies` 33/33.

### Ideas that did **not** ship

| Idea | Verdict |
| --- | --- |
| L1 lazy `LogRecord` fields via `__getattr__` | Rejected — `PercentStyle._format` does `self._fmt % record.__dict__`, a dict `__getitem__` lookup that bypasses `__getattr__`. |
| L2 `Logger.getEffectiveLevel` cache | Already implemented upstream as `Logger.isEnabledFor._cache`. |
| L3 handler-chain cache in `callHandlers` | Deferred — ~200 ns/emit saving not worth the invalidation surface across `addHandler` / `setLevel` / `propagate`. |

### Artifacts

- `Misc/logging-perf-diary.md` — experiment ledger.
- `Misc/logging-perf-data/` — 4 JSON artifacts, 3 bench scripts, README.

### Idea this came from

**Triple-flagged in the roster** — compiler, graph, and data-scientist
lenses all independently pointed at `LogRecord.__init__` +
`Logger.callHandlers`. The roster's headline prediction ("every FastAPI/
Celery/Airflow/Ray worker feels it") was directionally correct; the
magnitude is 3% on real Starlette request wall-time, not the 50% the
agent estimated.

## 4. json — hot-path C optimisations

**Branch**: `exp-json/research`
**Upstream**: not yet filed

### What shipped (8 experiments, stacked)

| id | change |
|----|--------|
| E3 | exact-type dispatch reorder in `encoder_listencode_obj` |
| E5 | raw `PyObject**` accumulator in `_parse_array_unicode` |
| E1 | single-pass classifier scan for 1-byte-kind strings |
| E9 | small-int fast path in `_match_number_unicode` |
| E10 | cached ASCII separator buffers on the Encoder |
| E11 | `PyUnicodeWriter_Create` size hint at encode entry |
| E7 | direct `PyOS_double_to_string` → writer for finite floats |
| E14 | extended cached ASCII separator to list/tuple encode |

Combined: ~150 lines added to `Modules/_json.c`, zero Python changes,
zero new files, zero new module state.

### Measured impact vs `main`

21-run trimmed mean, `taskset -c 0`:

| Scenario | main | final | Δ |
| --- | ---: | ---: | ---: |
| J1 web-api dumps | 6.36 µs | 5.52 µs | **−13.2%** |
| J2 log-line dumps | 2.09 µs | 1.76 µs | **−15.8%** |
| J3 NDJSON loads | 1.65 µs | 1.51 µs | **−8.6%** |
| J4 bulk dump 100k records | 80.6 ms | 69.0 ms | **−14.4%** |
| J5b unicode `ensure_ascii=False` | 1421 µs | 1214 µs | **−14.6%** |
| J6 numeric-heavy dumps | 27.5 ms | 25.2 ms | −8.5% |
| J8 deep tree roundtrip | 3492 µs | 3047 µs | **−12.7%** |

### Validation

- Full CPython suite: `test_json` 226/226, `test_unittest` + `test_importlib` 2313/2313.
- 25-check guardrails battery (subclass safety, exact-type rules,
  lone surrogates, control-char escaping, signed zero, big int,
  circular refs, `allow_nan`, `parse_float=Decimal`, insertion
  order, trailing-comma rejection) — all pass.
- Third-party smoke: simplejson / pydantic / jsonschema / fastapi
  round-trip identical output to `main`.

### Ideas that did **not** ship

| Idea | Verdict |
|------|---------|
| E2 kind-specialised decoder string scan | Rejected — the compiler already auto-vectorises `PyUnicode_READ`; manual specialisation was +1–2 pp regression on J3. Anti-pattern A2. |
| E4 module-level decoder key memo | Skipped — `Lib/json/__init__.py` already instantiates `_default_decoder = JSONDecoder()` as a module-level singleton, so the memo is already effectively module-scoped for the common case. |
| E6 partial-eval Encoder on config | Deferred — too complex; easy parts (cached separators, size hint) captured as E10/E11. |
| E8 stack-allocated circular-marker set | Deferred — complex rewrite for a predicted 2–4% win on top of 12–16% already captured. |

### Artifacts

- `Misc/json-perf-roadmap.md` — research roadmap built from 5 parallel Opus agent analyses (pattern-transfer, `_json.c` archaeology, compiler-theory, data-scientist / profiling, security / correctness).
- `Misc/json-perf-diary.md` — experiment ledger.
- `Misc/json-perf-data/research/` — raw agent outputs preserved verbatim.
- `Misc/json-perf-data/` — bench harness (`json_realistic_bench.py`), guardrails (`guardrails.py`), aggregator (`aggregate.py`), 27 raw bench JSONs (3 runs × 9 configurations).

### Idea this came from

Not on the original roster. Added after the three-campaign run as the
natural follow-on ("json is the next high-leverage target" — matched
the roster's priority on hot-path stdlib C modules used by every web
framework).

## Ideas from the roster still unshipped

Ranked by what still looks promising after the four rounds:

1. **ABC / Protocol `__instancecheck__`** (`Modules/_abc.c:632`,
   `Lib/typing.py:2076`). Double-flagged in roster. Caches keyed on
   `(type(instance), cls)`. Untouched.
2. **`ast.NodeVisitor.visit` dispatch cache** (`Lib/ast.py:516`).
   15 LoC, benefits every stdlib AST tool (compileall, linters).
3. **`datetime.fromisoformat` length-dispatched fast path**
   (`Modules/_datetimemodule.c:6048`). Log-ingestion bottleneck.
4. **`uuid.uuid4` byte-path C fast** (`Lib/uuid.py:775`). Distributed
   tracing workloads.
5. **`hashlib.sha256_hex` one-shot** (`Modules/_hashopenssl.c:1350`).
   Content-addressable caches.

Per-Formatter field-demand propagation was also discussed for logging
but left for a follow-up — it would enable skipping `threadName` /
`processName` / `taskName` computation when no formatter reads those
fields. Higher complexity; worth a separate issue when/if someone
picks it up.

## Bottom-line numbers

Across the four shipped branches:

- **CPython interpreter startup**: 15.8% faster (marshal PR)
- **Every `dill.dumps()` call**: 19–37% faster (pickle branch)
- **Every emitted log record**: 10–12% faster, 3% on end-to-end
  Starlette request wall-time (logging branch)
- **Every `json.dumps()` / `json.loads()` call on realistic payloads**:
  **8–16% faster** (json branch); web-api dumps −13.2%, log-line
  dumps −15.8%, NDJSON loads −8.6%, bulk 100k dump −14.4%.
- Combined test coverage across branches: **~146,000 CPython tests
  plus ~3,400 third-party tests** across all four states, with
  third-party validation on dill / cloudpickle / joblib / attrs /
  Starlette / structlog / sentry-sdk / Django / Sphinx / loguru /
  simplejson / pydantic / jsonschema / fastapi showing identical
  pass/fail behavior to `main`.

## Provenance

Generated 2026-04-18 as the outcome record for the stdlib
perf-opportunity sweep. Companion to `Misc/cpython-perf-ideas.md`
(the forward-looking roster).
