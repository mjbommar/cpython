# CPython stdlib perf-opportunity brainstorm

Working notebook for performance ideas in the CPython standard library
and C accelerator modules, generated as a follow-up to the marshal
safe-cycle + perf-recovery PR (python/cpython#148700).

This file is **not a proposal** — it's a ranked roster of targets
produced by crossing three independent reviews of the codebase, one
per perspective (compiler theorist, graph / algorithms theorist,
data-scientist with a production-workload lens). Each idea includes a
concrete `file:line` pointer, the optimization-theoretic reason the
current code is under-specialized, a payoff estimate, and a scope /
effort estimate. Top picks are called out at the end with an
implementation-order rationale.

Branch: `perf-ideas`, no dependencies on the marshal PR. Safe to update
in place.

## Methodology

Three reviews of the tree at commit `2faceeec5c0` (main tip), each
framed around a specific lens:

- **Compiler theorist**: dispatch specialization, polymorphic inline
  caches, escape analysis, bytecode fusion, type-feedback, descriptor
  short-circuiting.
- **Graph / algorithms theorist**: traversal topology, prepasses,
  dominator caches, SCC detection, memoization keyed on the right
  graph invariants.
- **Data scientist / production workloads**: what Ray/Dask/joblib,
  pytest/ruff/mypy, FastAPI/Django, Airflow/Celery, pandas/polars,
  sklearn/PyTorch actually spend time on — and which CPython hot spots
  would move wall-clock numbers that a user watching `py-spy` would
  feel.

Each review produced 12 ranked ideas (36 total, minus overlap). Anything
**already known in this PR's context** was explicitly excluded — marshal
(shipped), pickle memo internals (already hand-optimized), pickle
exact-container fast paths for pure Python (already done in the
follow-up branch), copy.deepcopy memo as a structure (dict is correct),
struct format cache (already present), `_json.c` string-scan via
`memchr` and homogeneous-dict fast path (on our radar — **substantially
done in `exp-json/research` 2026-04-18: see
`Misc/json-perf-diary.md`; the branch now has third-party validation
and is ready to split into filing candidates**), `_csv.c` bulk scan
(on our radar).

Reusable service-style profiling harnesses for framework-heavy paths now
live in `Misc/service-profile-data/` on this branch. They are not
optimization ideas by themselves; they exist to make FastAPI and Celery
profiling repeatable across future experiments and to expose which
stdlib and builtins / C-backed paths dominate under service-ish loads.
The current harness set includes `fastapi`, `celery`, `django`,
`jinja2`, and `jsonschema`.

One service-profile follow-up was explicitly investigated and rejected:
generic `getattr` / dict / type-lookup fast paths in
`Objects/object.c` + `Objects/typeobject.c`. Full notes live in
`exp-attr/generic-getattr-fastpaths` (`Misc/attr-getattr-perf-diary.md`)
on that branch. Short version:

- stackref-native generic-`getattr` (`_PyObject_GetAttrStackRef`)
  produced nice micro wins but broke Django import (`Field.remote_field`
  lookup failure)
- `find_name_in_mro()` own-dict-first looked like the smallest safe
  patch, but failed `test_descr` and hit an MRO / re-entrant-lookup
  regression including a subprocess segfault in
  `test_type_lookup_mro_reference`
- exact-dict-only known-hash instance-dict lookup was the only clearly
  safe variant, and it was too close to noise on the real workloads to
  justify a PR

Conclusion: this family is still hot, but the obvious C fast paths sit
too close to descriptor / MRO correctness boundaries. Keep it off the
recommended queue unless we come back with a deeper interpreter-level
specialization plan.

Another service-profile follow-up was explored more directly on
`exp-asyncio/eventloop-hotpaths`
(`Misc/asyncio-eventloop-perf-diary.md` on that branch). That branch
used a real loopback `uvicorn` + `fastapi` corpus rather than
`TestClient`, plus timer / selector micros, to check whether the
service hot spots in `asyncio` and `selectors` had a small pure-Python
patch worth filing. Short version:

- `TimerHandle.__lt__` exact-type and tiny `Handle` / `call_at` debug
  guard cleanups did move timer-heavy micros, but the real ASGI and
  socket-loop workloads stayed near noise
- `_run_once` local-binding rewrites were flat-to-worse and should be
  treated as a dead end
- the cleanest surviving patch was an `EpollSelector.select`
  exact-event-mask fast path; it passed `test_asyncio`,
  `test_selectors`, `test_socket`, and `test_heapq`, plus third-party
  import smoke (`anyio`, `uvicorn`, `starlette`, `fastapi`, `httpx`,
  `django`, `celery`, `gunicorn`, `prompt_toolkit`)
- even the best confirmatory result was only modest:
  roughly `-4%` on a selector/socketpair micro, `-3%` on a small
  asyncio echo workload, and roughly flat on real `uvicorn` loopback
  requests

Conclusion: `asyncio` event-loop hot spots are real, but the first
round of pure-Python local rewrites did not produce a strong filing
candidate. Keep `selectors.EpollSelector.select` exact-mask handling as
a low-priority follow-up, not the next PR target.

## Convergence — ideas that surfaced on multiple lists

These are the strongest signals. When a compiler theorist, a graph
theorist, and a workload-focused data scientist all independently point
at the same code, that's a load-bearing observation.

### Triple-flagged

1. **`logging.LogRecord.__init__` + `Logger.callHandlers` + `getEffectiveLevel`**
   - `Lib/logging/__init__.py:295` (`LogRecord.__init__`), `:1724`
     (`callHandlers`), `:1754` (`getEffectiveLevel`)
   - Three lenses:
     - *Compiler*: dead-store / escape analysis on a monomorphic record —
       eagerly populates `os.path.basename`, `os.path.splitext`,
       `threading.get_ident`, `threading.current_thread().name`,
       `sys.modules.get('multiprocessing')` + `mp.current_process().name`,
       `os.getpid()`, and on 3.12+ `asyncio.current_task().get_name()`,
       but the configured formatter often reads only 3–5 fields.
     - *Graph*: logger hierarchy is a tree; `callHandlers` walks
       `self -> parent -> ...` on every emit, `getEffectiveLevel`
       walks the same chain separately, neither caches the result of a
       dominator walk that invalidates rarely.
     - *Data scientist*: every FastAPI request, every Celery task,
       every Airflow task-state change emits at least one INFO record;
       production logger counts are 1k–10k records/sec and the
       per-record cost is measurable in `py-spy`.
   - **Plan**: lazy `LogRecord` attributes (compute on first `__getattr__`
     rather than in `__init__`); cache `(effective_level,
     flattened_handler_chain)` on each `Logger` with an invalidation
     counter bumped by `setLevel` / `addHandler` / `removeHandler` /
     `propagate` changes.
   - **Payoff**: high. Plausibly cuts per-record cost by ~50%; saves
     1–4 ms/s on a typical web service; compounds across every Python
     workload that logs.
   - **Scope**: medium, pure Python. Back-compat risk: custom formatters
     that rely on attribute presence at `record.__dict__` level (JSON
     loggers). Mitigate by making laziness opt-in initially via
     `logging.setLogRecordFactory`.
   - **2026-04-18 follow-up**:
     - The original lazy-attribute plan was rejected. `%` formatting
       reads `record.__dict__` directly, so `__getattr__` laziness
       does not preserve semantics.
     - `Logger.getEffectiveLevel` was not actually open work:
       `Logger.isEnabledFor` already carries a per-level cache.
     - The investigation split into two branch-local diaries:
       `exp-logging/hot-path` (Python-only caches in
       `LogRecord.__init__` / `_is_internal_frame`) and
       `exp-logging/c-helpers` (the same ideas prototyped inside
       `_logging`).
     - The Python-only branch remained the clean PR candidate. The
       C-helper branch exposed four semantic hazards that had to be
       fixed: unhashable `os.PathLike` cache keys, stale main-thread
       names, `_style._fmt` rebinding after `usesTime()` caching, and
       32-bit overflow when reading `_startTime`.
     - After those fixes, the C-helper branch still beat stock 3.15 on
       every emitted-path logging scenario we care about, but the extra
       gain over the Python-only branch was small and noisy. Long-term
       conclusion: keep the Python-only hot-path work as the low-risk
       first PR and treat deeper C acceleration as a separate follow-up.
     - A broader 2026-04-18 rerun against wrapper/framework logging
       paths (`structlog`, `uvicorn`, `flask`, `django`, `celery`)
       still showed real wins over rebuilt `main` at about `-8%` to
       `-14%` per emitted record, so the C-helper branch is technically
       sound. That said, one extra `_loggingmodule.c` cleanup idea
       (`PyObject_CallMethodNoArgs` tightening for the dynamic helper
       calls) was flat-to-worse and got reverted. Recommendation
       unchanged: do the Python-only branch first.

### Double-flagged

2. **ABC / Protocol `__instancecheck__`**
   - `Modules/_abc.c:632` (the `__class__` attribute lookup),
     `Lib/_py_abc.py:108` (virtual-subclass DAG walk),
     `Lib/typing.py:2076` (Protocol structural check)
   - *Compiler*: descriptor-protocol overhead where `Py_TYPE(x)` would
     suffice for non-proxy objects; full `PyObject_GetAttr(&_Py_ID(__class__))`
     runs on every `isinstance(x, SomeABC)`.
   - *Graph*: virtual-subclass registration forms a DAG; a negative
     `__subclasscheck__` walks the full DAG recursively; caching is
     per-query-class only, not on intermediate nodes encountered on the
     DFS.
   - **Plan**: (a) in `_abc.c`, add a `Py_TYPE` fast path for ordinary
     receivers (fallback to `__class__` only when the type overrides
     `tp_getattr` or has a non-default `__class__` descriptor);
     (b) in `typing.py` / `_py_abc.py`, add a
     `(type(instance), cls) -> bool` cache invalidated by
     `ABCMeta._abc_invalidation_counter`.
   - **Payoff**: medium-high. `isinstance` against ABCs / Protocols is
     everywhere in typed codebases (Pydantic, FastAPI dependency
     injection, tight validator loops).
   - **Scope**: small-to-medium. Touches one C file plus `typing.py`.
   - **2026-04-18 follow-up**:
     - Investigated on `exp-abc/instancecheck-cache`; full notes live in
       `Misc/abc-instancecheck-perf-diary.md` on that branch.
     - The best result was the smaller `_abc.c` patch: check
       `Py_TYPE(instance)` against `_abc_cache` before fetching
       `instance.__class__`.
     - Averaged over two runs, that C-only patch improved
       `inspect.isawaitable` by about `-7.7%`, `httpx` request-data
       encoding by `-2.1%`, `typeguard` mapping checks by `-1.8%`,
       `jsonschema._utils.equal` by `-4.7%`, and direct
       `jsonschema.protocols.Validator` checks by `-8.6%`.
     - The more aggressive exact-type fast path won harder on some
       positive-hit micros, but lost its edge on the representative
       real-workload average and added more proxy overhead.
     - The `typing.py` protocol type-cache experiment should be dropped:
       it was performance-unstable and could return false positives for
       later instances of the same type when protocol satisfaction came
       from instance attributes.
   - Validation on the final branch state included `test_abc`,
     `test_typing`, `test_inspect`, `test_context`,
     `test_collections`, and `test_pathlib`.
   - **2026-04-18 deeper follow-up**:
     - Re-opened on `exp-isinstance/type-lookup` with a broader search
       over `_abc.c` plus `typeobject.c`, and a workload corpus covering
       `inspect`, `httpx`, `typeguard`, `jsonschema`, Django, and
       Celery.
     - Best aggregate result was a combined patch:
       - `_abc.c`: subtype-cache check against `_abc_cache`
       - `PyType_IsSubtype()`: exact/base/object direct-edge shortcut
       - `find_name_in_mro()`: own-dict-first before the full MRO walk
     - Representative deltas vs rebuilt baseline:
       `inspect.isawaitable -10.3%`, `httpx` request-data encoding
       `-10.9%`, `typeguard` mapping checks `-4.8%`,
       `jsonschema._utils.equal -3.8%`, direct
       `jsonschema.protocols.Validator -6.2%`,
       `jsonschema.validate -0.6%`, minimal Django request `-2.4%`,
       Celery eager dispatch `-2.4%`.
     - Tradeoff: semantics stayed correct, but the fake-`__class__`
       proxy micro regressed by about `+70%`. The new `test_abc`
       regression confirms proxy behavior is still correct.
     - Safer runner-up: the standalone `PyType_IsSubtype` direct-edge
       fast path. It is smaller, keeps the proxy micro healthy, and
       still wins on `httpx`, Django, and Celery, but it gives back some
       ground on `jsonschema` protocol-heavy cases.
     - Guarding the `_abc` subtype-cache behind a default-`__class__`
       descriptor check avoided the proxy slowdown, but cost too much on
       the negative ABC miss path to be the preferred direction.
     - Validation on the combined branch state:
       - stdlib: `test_abc test_typing test_inspect test_context
         test_collections test_pathlib`
       - third-party: `691` local `jsonschema` / `referencing` tests
         passed (excluding the two suite-checkout-dependent files)
     - Updated recommendation: prefer the broader
       `exp-isinstance/type-lookup` result if we want the strongest
       service-workload win; keep the standalone `PyType_IsSubtype`
       patch in reserve as the lower-risk fallback.

## Single-lens standouts worth building

Ideas that only one lens surfaced but with high individual ROI.

### From the compiler-theorist pass

3. **`_sre/sre.c:2725` match-object lazy group materialization**
   - `Modules/_sre/sre.c:2725`–`:2785`, allocation at line 2741 sizes for
     `2*(pattern->groups+1)` slots and fills them unconditionally.
   - Lens: type-feedback / profile-guided lazy materialization. Real
     callers overwhelmingly do `if pattern.search(s):` or `.group(0)`
     only; the full mark table is dead state.
   - Plan: populate `mark[]` on first `group()`/`groups()`/`groupdict()`
     access. Optionally a truthiness-sentinel fast path for `if m:`
     contexts that skips `PyObject_GC_NewVar` entirely.
   - Payoff: high on regex-heavy paths (`_strptime`, tokenizers, config
     loaders).
   - Scope: medium, single C file.

4. **`Lib/dataclasses.py:477` skeleton-cached `__init__` instead of
   `exec`-per-class**
   - Currently every `@dataclass` decoration synthesizes a source string
     (`_field_init` at `:590`, `_init_fn` at `:669`) and runs it through
     the full Python compile pipeline.
   - Lens: bytecode construction via source-string fusion is an
     anti-pattern when we already know the target shape.
   - Plan: cache a compiled skeleton `CodeType` keyed by
     `(tuple(field_kinds), frozen, slots)`, patch in names/defaults.
   - Payoff: high on cold start for dataclass-heavy apps (Pydantic-adjacent,
     attrs-alikes, ORM row types), negligible steady-state.
   - Scope: medium-invasive.

5. **`Lib/functools.py:35` `update_wrapper` bulk attribute copy**
   - Six-attribute interpreted loop with per-attribute try/except plus a
     `wrapper.__dict__.update(wrapped.__dict__)` that usually has nothing
     to merge.
   - Plan: `_functools._update_wrapper` C helper doing a straight-line
     sequence of `PyObject_GenericSetAttr` calls.
   - Payoff: medium on cold import.
   - Scope: small.

6. **`Lib/_strptime.py:534` lock-free format cache**
   - Current cache holds `_cache_lock` for both lookup and compile;
     high-QPS datetime parsing serializes on the lock.
   - Plan: swap to `functools._lru_cache_wrapper` (lock-free fast path)
     or a bounded tuple-swap inline cache.
   - Payoff: medium-high for threaded log-ingest workloads.
   - Scope: small-to-medium.

7. **`Lib/typing.py:1716` deprecation warning memoization**
   - `_UnionGenericAliasMeta.__instancecheck__` emits a `warnings._deprecated`
     every time, paying the warnings-machinery cost per `isinstance`.
   - Plan: one-shot flag to silence after the first emission.
   - Payoff: small in aggregate but near-free to add.
   - Scope: trivial.

8. **`Python/traceback.c:636` lazy PEP 657 location-info decode**
   - `PyException_SetTraceback` eagerly decodes the compressed location
     table; exception-heavy control-flow code pays on every raise.
   - Plan: decode only when `traceback.format_exc()` / print is called.
   - Payoff: medium on exception-heavy microbenchmarks.
   - Scope: invasive — touches the raise path.

### From the graph-theorist pass

9. **`Lib/copy.py:110` SCC-based `deepcopy` memo elision**
   - Earlier ruled out because the memo key must be arbitrary
     `id(obj)`. Graph lens reframes it: real graphs are nearly always
     DAGs, and nearly all nodes are unique refs in their subgraph. A
     Tarjan-style prepass (`seen_once` vs `seen_many`) lets us skip
     `memo.get` + `memo[d]=y` + `_keep_alive` for `seen_once` subgraphs.
   - Payoff: medium-high on JSON-like DAG payloads (Django forms,
     dataclass trees, configuration state).
   - Scope: small (~100 LoC plus a helper).

10. **`Lib/importlib/_bootstrap.py:1140` meta_path short-circuit cache**
    - `sys.meta_path` walked linearly for every `_find_spec` call.
      `BuiltinImporter` rejects 99% but still pays a bound-method
      lookup and call.
    - Plan: negative-result cache keyed by `(name_first_segment, epoch)`;
      bump epoch on `sys.meta_path` mutation.
    - Payoff: medium for import-heavy workloads (pytest, Django).
    - Scope: small-medium.

11. **`Python/gc.c:788` propagate "all-atomic-descendants" flag**
    - Long-lived config dicts/lists are tracked and re-traversed on
      every full-gen collection even when they provably cannot
      contain cycles.
    - Plan: during scan, if a container's `tp_traverse` reports zero
      tracked children, set a flag; skip traversal on subsequent
      scans until mutation.
    - Payoff: medium-high for long-running apps with stable config
      state.
    - Scope: medium-large; coordinates with container mutation hooks
      (e.g. `ma_version_tag`).

12. **`Lib/ast.py:516` `NodeVisitor.visit` dispatch table memoization**
    - String concatenation `'visit_' + node.__class__.__name__` plus
      `getattr` on `self` for every AST node. A visitor with 10
      overrides over a 100k-node AST does 100k `getattr` misses that
      all fall through to `generic_visit`.
    - Plan: some form of dispatch cache built on first encounter of a
      node type.
    - Payoff: medium. Every stdlib AST tool (compileall, linters — flake8,
      pyflakes, bandit, codemods) benefits.
    - Scope: tiny (~15 LoC).
    - **2026-04-18 follow-up**:
      - Investigated on `exp-ast/nodevisitor-cache`; full notes in
        `Misc/ast-nodevisitor-perf-diary.md` on that branch.
      - The fastest prototype was a per-instance bound-method cache, but
        it changed dynamic lookup semantics: monkeypatching
        `visitor.visit_Name` after the first visit stopped taking effect,
        and `__getattr__`-driven visitor lookup was only consulted once
        per node type.
      - The recommended patch is therefore the safer **method-name
        cache**: memoize only `"visit_" + node_type.__name__`, but keep
        `getattr(self, ...)` on every dispatch.
      - That conservative patch still showed meaningful wins in the
        branch measurements: roughly `-15.7%` on recursive generic
        traversal, `-15.1%` on `pygettext`, `-12.8%` on `pyupgrade`,
        `-10.2%` on Black's notebook-magic visitors, and `-6.1%` on
        `_ast_unparse`, while preserving current behavior.
      - Validation on the branch included `test_ast`, `test_unparse`,
        `test_pyclbr`, and `test_tools.test_i18n`.

13. **`Lib/unittest/loader.py:408` per-directory realpath memo**
    - `_find_test_path` does `os.path.realpath` on every test file and
      expected-dir; real paths share huge prefixes.
    - Plan: directory-level realpath memo inside `discover`.
    - Payoff: medium for mono-repos with thousands of tests.
    - Scope: tiny.

14. ~~**`Lib/json/decoder.py:349` module-level key-interning LRU**~~
    **SKIPPED after investigation**: `Lib/json/__init__.py:244`
    already instantiates `_default_decoder = JSONDecoder()` as a
    module-level singleton, so the memo is already effectively
    module-scoped for the common `json.loads(s)` call. Per-instance
    memo only misses when the user passes a hook or `cls=`.
    See `exp-json/research` / `Misc/json-perf-diary.md` for the
    8 other json experiments that did land (−13 to −16% on
    realistic encoder scenarios, −8.6% on NDJSON decode).
    A deeper 2026-04-18 follow-up also validated the branch on
    `httpx`, `starlette`, `fastapi`, `flask`, `django`, and
    `dataclasses_json` wrapper paths with byte-identical smoke output
    and package-backed wins ranging from about `-3%` to `-15%`.
    Two smaller follow-up ideas were rejected after measurement:
    exact-`str` key refcount elision and an exact-dict `sort_keys`
    path. Updated recommendation: treat `exp-json/research` as ready
    to split into encoder-first PRs rather than leaving it in pure
    research status.

15. **`Lib/traceback.py:1215` exception-graph SCC prepass**
    - `TracebackException` creates full formatted frames for every
      reachable exception via `__cause__` / `__context__` / group
      children, even when cycles / shared context would prune the work.
    - Plan: id-only prepass to compute the DAG shape; do stack
      extraction only for surviving nodes in topological order.
    - Payoff: low-medium; matters for exception groups with shared
      contexts in async code.
    - Scope: small.

### From the data-scientist pass

16. **`Lib/pathlib/__init__.py:174` `PurePath.__truediv__` fast path**
    - Every `path / "segment"` goes through `with_segments(*pathsegments)`
      at `:159` and back through full `__init__` at `:140`. Properties
      (`parts`, `parent`, `_str_normcase`) all use
      AttributeError-as-cache, which is 2–3× slower than a dict lookup
      on a hit.
    - Plan: specialized `(PosixPath, str)` fast path; replace
      AttributeError-cache idiom with `__slots__` + `is None`.
    - Payoff: medium. pytest collection / ruff / mypy / Black are
      path-heavy; 5–15% of collection time is pathlib.
    - Scope: medium. Natural first C-accelerator target (`_pathlib`).

17. **`Modules/_datetimemodule.c:6048` `fromisoformat` parser-entry fast
    path**
    - 99% of real-world ISO strings are `YYYY-MM-DDTHH:MM:SS.ffffff`
      (length 26) or `YYYY-MM-DDTHH:MM:SS+HH:MM` (length 25). The
      current code does a generic byte-by-byte separator scan.
    - Plan: if `len(s) in {26, 25, 19}`, direct digit-unroll.
    - Payoff: 2–3× on the common case. Log-aggregation bottleneck.
    - Scope: small (~150 LoC of C).
    - **2026-04-18 follow-up**:
      - Investigated on `exp-datetime/fromisoformat-fastpath`; full
        notes live in `Misc/fromisoformat-perf-diary.md` on that
        branch.
      - The winning experiment was the smaller entry fast path inside
        `datetime.datetime.fromisoformat()`:
        - skip `_sanitize_isoformat_str()` and
          `PyUnicode_AsUTF8AndSize()` for ASCII input
        - short-circuit separator discovery for obvious
          `YYYY-MM-DD` / `YYYYMMDD` prefixes
      - A broader family-wide fast path for `date` / `time` did not
        justify the extra patch surface and was dropped.
      - Clean sequential reruns against rebuilt `main` showed the final
        patch improving direct datetime micros by about `-8.9%`
        (`YYYY-MM-DDTHH:MM:SS`), `-7.9%` (microseconds), `-4.8%`
        (timezone), and `-3.4%` (week-date).
      - Representative wrappers were mixed but mostly near-flat:
        `dataclasses_json` about `-4.8%`, `jsonschema` `-2.1%`,
        `qcore` `-2.4%`, while `sqlalchemy` wrappers ranged from
        `+0.7%` to `+3.4%` and `cattrs` was `+2.6%`.
      - Validation on the branch included a full rebuild plus
        `test_datetime`.
      - Long-term conclusion: this is still a reasonable narrow C
        micro-PR, but the safe version is a single-digit optimization,
        not the original 2–3x hypothesis. A true digit-unrolled parser
        would need a separate, more invasive experiment.

18. **`Lib/uuid.py:775` `uuid4` byte-path fast**
    - `int.from_bytes(os.urandom(16))` → big-int mask → `int.to_bytes(16)`:
      four big-int allocations per UUID. Distributed tracing mints
      dozens of UUIDs per HTTP request.
    - Plan: C-level `_uuid.uuid4()` that operates directly on bytes,
      bypasses `UUID.__init__` validation.
    - Payoff: ~4× on the common case; meaningful for tracing-heavy
      microservices.
    - Scope: small; extend existing `_uuid` C module.
    - **2026-04-18 follow-up**:
      - Investigated on `exp-uuid/c-fastpath`; full notes live in
        `Misc/uuid4-c-fastpath-perf-diary.md` on that branch.
      - The winning shape is a small `_uuid.generate_random_int()`
        helper plus `Lib/uuid.py` gating:
        - Windows: `BCryptGenRandom`
        - BSD / macOS: `arc4random_buf()` or `arc4random()`
        - Unix: blocking `getrandom(..., 0)` with `ENOSYS` fallback
          through `getentropy()` and then `/dev/urandom`
        - keep the pure-Python fallback when the helper is absent
      - The final branch also restored `_uuid` to the limited C API by
        using the public 3.14 native-byte long APIs instead of the
        private `_PyLong_FromByteArray`.
      - Rebuilt-binary confirm result:
        - `uuid.uuid4()` improved from about `543 ns` to `351 ns`
          (`-35.4%`)
        - `uuid.uuid7()` stayed effectively flat (`925 ns -> 915 ns`)
      - The portable final helper gave back a little speed versus the
        rough Linux-only prototype (`329 ns`), but still retained most
        of the win.
      - `test_uuid` passed on the final branch state, and the branch now
        includes a targeted fallback test to pin the pure-Python path
        when the helper is unavailable.
      - Remaining open question: the runtime design now looks sound, but
        the branch still relies on a broader `_uuid` build-shape change
        so the helper can exist even without external `libuuid`
        support. That is a policy / build-system decision separate from
        the perf gain itself.
      - Long-term conclusion: this is a promising small C optimization,
        but it should only be treated as PR-ready once the `_uuid`
        module-shape question has been validated on fork CI across
        Windows and macOS.

19. **`Modules/_hashopenssl.c:1350` one-shot `sha256_hex` API**
    - No `hashlib.sha256_hex(data)` today; users pay three C/Python
      transitions (`new()` / `update()` / `hexdigest()`) per hash, and
      EVP allocation dominates for sub-1KB inputs.
    - Plan: add one-shot helpers.
    - Payoff: 30–40% on small inputs. DVC, artifact caches,
      content-addressable CI, Nix-style stores.
    - Scope: small.

20. **`Lib/re/__init__.py:163` id-keyed compile cache fast path**
    - Hot code does `re.match(r'literal', s)` where the literal string
      is the same Python object each call. Current cache is keyed by
      `(type(pattern), pattern, flags)` tuple; lookup + hash is ~200ns.
    - Plan: tiny `id(pattern)` LRU in front of the real cache.
    - Payoff: 30–50ns per call; visible at 1M+ calls/sec.
    - Scope: tiny.

21. **`Modules/_heapqmodule.c:26` specialized comparator for
    `(float, obj)` tuples**
    - asyncio's `_scheduled` heap is always `(deadline:float,
      counter:int, callback)`. Current sift uses
      `PyObject_RichCompareBool`, descending through
      `tuple.__lt__` → `float.__lt__` → C double compare, plus INCREF
      traffic per compare.
    - Plan: specialized `_siftup_tuple_first_float` path.
    - Payoff: event-loop-heavy apps spend 5–10% in heapq; cut in half.
    - Scope: medium.
    - **2026-04-18 follow-up**:
      - Investigated on `exp-heapq/asyncio-tuple-compare`; full notes
        live in `Misc/heapq-asyncio-perf-diary.md` on that branch.
      - The original asyncio-specific tuple hypothesis turned out to be
        stale. Current `asyncio` stores `TimerHandle` objects, not
        `(when, seq, handle)` tuples, so `_heapq` tuple specialization
        is not an asyncio-service optimization by itself.
      - The good news is that the tuple / namedtuple idea is still real
        elsewhere. `sched`, `kombu.asynchronous.timer`, and
        `celery.beat` all rely on tuple-like heap items with
        `float` / `int` / `int` ordering prefixes.
      - Best branch result was a small `_heapq` helper keyed on:
        - tuple-like object (`PyTuple_Check`)
        - built-in tuple rich-compare slot
        - length `3` or `6`
        - direct compare of slot `0` exact `float`, slot `1` exact
          `int`, then slot `2` exact `int`
        - fallback to the normal `PyObject_RichCompareBool(..., Py_LT)`
          otherwise
      - Representative deltas vs rebuilt baseline:
        `M2_namedtuple3_pushpop -24.3%`,
        `M3_sched_event_pushpop -20.6%`,
        `M4_namedtuple3_heapify_pop -22.2%`,
        `R1_sched_run -13.2%`,
        `R3_kombu_timer -4.9%`,
        while the real loopback `uvicorn` / `fastapi` workloads stayed
        effectively flat.
      - A longer focused rerun against rebuilt `main` kept the wrapper
        results favorable: `sched` about `-13.3%`, `dateutil`
        about `-0.9%`, and `kombu` about `-0.8%`.
      - Validation on the final branch state:
        - stdlib: `test_heapq test_sched test_queue test_asyncio`
        - third-party: `484` local `jsonschema` tests passed once the
          external-suite-checkout file was excluded
        - import smoke passed for `dateutil`, `kombu`, `celery`,
          `jsonschema`, `uvicorn`, `starlette`, `fastapi`, `httpx`,
          `anyio`, `asgiref`, and `gunicorn`
      - Remaining theorized risk: if the first compared slot is an
        exact `float` `NaN`, the current helper can diverge from normal
        tuple comparison because it falls through to slots `1` and `2`
        after both `<` and `>` checks on slot `0` return false. That
        edge case was not observed in the tested corpora, but it should
        be fixed or regression-tested before treating the branch as
        PR-ready.
      - Updated recommendation: keep this as a plausible medium-priority
        `_heapq` PR for tuple-heavy heaps, but do not frame it as the
        next asyncio optimization branch.

22. **`Modules/_collectionsmodule.c:2538` Counter specialization**
    - Current fast path still allocates `PyLong(n+1)` per increment.
      For billions of tokens this is billions of allocations.
    - Plan: open-addressed `str/int → Py_ssize_t` counter table;
      materialize a dict at end.
    - Payoff: 2–3× on large-stream Counter construction.
    - Scope: medium.

23. **`Lib/copy.py:62` shallow `copy.copy` fast path**
    - For the 90% case (user class with `__dict__`, no `__copy__`
      override), generic `_reconstruct` builds a reduce tuple, calls
      `__new__`, calls `__setstate__`. Optimal shallow copy is
      `new = cls.__new__(cls); new.__dict__ = inst.__dict__.copy()`.
    - Plan: fast path before the dispatch table.
    - Payoff: SQLAlchemy unit-of-work, Pydantic `.model_copy()`, FastAPI
      response serialization.
    - Scope: small.

## Recommended implementation order

Ranked by **(triple-convergence) × (concrete first-diff) × (ecosystem
reach)**. Each target stands alone as a PR; none depends on another.

| Rank | Target | Effort | Confidence | PR-shape |
|---|---|---|---|---|
| **1** | Logging hot path — pure-function caches in `LogRecord` / `findCaller`; optional C-helper follow-up | Medium | High (3×) | Pure Python first; C helper separate |
| **2** | AST `NodeVisitor.visit` method-name cache | Tiny | High | Pure Python, validated branch |
| **3** | `isinstance` / ABC / type-lookup fast paths (`_abc.c` + small `typeobject.c` helpers) | Small-Medium | Medium-high | Validated branch; lower-risk `PyType_IsSubtype` subset exists |
| **4** | `datetime.fromisoformat` ASCII / separator entry fast path | Small | Medium-high | Single C file |
| **5** | `pickle` type-strategy dispatch cache (carry-over from earlier #2 list) | Medium | Medium | Pure Python, composes with Exp #4 |
| **6** | `uuid.uuid4` byte-path C fast | Small | High | Extend `_uuid` |
| **7** | `hashlib.sha256_hex` one-shot | Small | Medium | Stdlib API addition |
| **8** | `copy.deepcopy` SCC prepass | Small | Medium | Pure Python |
| **9** | `re.compile` id-keyed cache fast path | Tiny | Medium | Pure Python |
| **10** | `dataclasses` skeleton-cached `__init__` | Medium-invasive | Medium | Pure Python |

## Non-goals / explicitly not recommended

- **The interpreter loop (`Python/ceval.c`)** — the Faster CPython team
  actively specializes it. Do not duplicate work there.
- **Introducing new C extension modules from scratch.** All picks above
  either extend an existing module or stay in pure Python.
- **Wire-format changes** (marshal, pickle protocol). The shipped work
  specifically preserves wire compat; any ideas here should too.
- **Breaking back-compat on public attributes or `record.__dict__`
  lookups.** `LogRecord.thread` and `record.__dict__['thread']` style
  access are both real compatibility constraints for logging work.

## Provenance

Generated 2026-04-17 by crossing three independent code reviews of
commit `2faceeec5c0`. Raw agent transcripts archived under
`/tmp/claude-1000/.../tasks/` on the authoring machine, not
reproduced here. Cite this file as the synthesis, not the agents
individually — they're inputs, not authorities.
