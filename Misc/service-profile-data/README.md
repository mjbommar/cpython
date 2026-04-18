# Package Profiling Harnesses

Reusable framework-heavy and pure-Python-package workloads for profiling
a CPython build on something closer to real application behavior than
isolated micros.

Current workloads:

- `fastapi_service_workload.py`
  - in-process FastAPI app
  - request parsing, dependency injection, Pydantic validation,
    response-model serialization, Starlette/httpx test transport
- `django_service_workload.py`
  - in-process Django client + view workload
  - URL resolving, request parsing, form validation, template rendering
- `celery_service_workload.py`
  - Celery app using `memory://` broker and `cache+memory://` backend
  - default mode uses eager execution for fast iterative profiling
  - optional worker mode starts a real in-process worker with
    `pool="solo"`
  - exercises task dispatch, tracing, Kombu JSON serialization, and
    result retrieval without requiring Redis or RabbitMQ
- `jinja2_template_workload.py`
  - pure-Python Jinja2 render loop
  - template expansion, dict/attribute lookup, string-heavy output
- `jsonschema_validate_workload.py`
  - pure-Python schema validation loop
  - nested object/array traversal, regex checks, repeated type checks
- `service_cprofile.py`
  - wraps either workload with `cProfile`
  - defaults to stdlib-only and builtins/C-backed hotspots
  - optional `--show-overall` includes framework wrappers too

## Dependencies

These scripts assume the interpreter under test can import:

- `fastapi`
- `httpx`
- `django`
- `celery`
- `cffi`
- `jinja2`
- `jsonschema`

On this machine those packages live in `/tmp/perf-extra-pkgs`, so the
typical invocation is:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python Misc/service-profile-data/service_cprofile.py fastapi
```

## Recommended profiling flow

### 1. Deterministic Python hotspot pass

Use `cProfile` first when you want actionable function names in stdlib,
third-party Python, and builtins/C-backed callables:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/service-profile-data/service_cprofile.py fastapi \
  --iterations 3000 --warmup 300 --limit 30

PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/service-profile-data/service_cprofile.py celery \
  --iterations 1500 --warmup 100 --celery-mode eager --limit 30

# deeper, slower worker-path pass
PYTHONPATH=/tmp/perf-extra-pkgs ./python \
  Misc/service-profile-data/service_cprofile.py celery \
  --iterations 30 --warmup 5 --celery-mode worker --limit 30
```

### 2. Lower-overhead sampling pass

Use Tachyon (`profiling.sampling`) when you want a broader view with
less profiler distortion:

```bash
PYTHONPATH=/tmp/perf-extra-pkgs ./python -m profiling.sampling run \
  --native --sort=cumtime -l 40 \
  Misc/service-profile-data/fastapi_service_workload.py \
  --iterations 5000 --warmup 300

PYTHONPATH=/tmp/perf-extra-pkgs ./python -m profiling.sampling run \
  --native --sort=cumtime -l 40 \
  Misc/service-profile-data/celery_service_workload.py \
  --iterations 2000 --warmup 100 --mode eager

# deeper, slower worker-path pass
PYTHONPATH=/tmp/perf-extra-pkgs ./python -m profiling.sampling run \
  --native --sort=cumtime -l 40 \
  Misc/service-profile-data/celery_service_workload.py \
  --iterations 40 --warmup 5 --mode worker
```

`--native` is useful here because it makes time spent outside Python
frames visible as `<native>` stack segments.

### 3. Native symbol pass with Linux perf

When the host allows `perf_event_open` access, use Linux `perf` for the
actual C/runtime symbol view:

```bash
perf record -g -- ./python -X perf \
  Misc/service-profile-data/fastapi_service_workload.py \
  --iterations 5000 --warmup 300

perf report --stdio --sort comm,dso,symbol | sed -n '1,120p'
```

On this machine `perf_event_paranoid=4`, so `perf record` is blocked for
unprivileged users. The workload scripts are still ready for that mode
once permissions are opened up.

## Current snapshot on this machine

These are first-pass results from `/tmp/cpython-main-bench/python` with
dependencies from `/tmp/perf-extra-pkgs`.

### FastAPI

`cProfile` on the in-process `TestClient` path shows the request stack
dominated by:

- `starlette.testclient.TestClient.post`
- `httpx.Client.request` / `send`
- `starlette.testclient._TestClientTransport.handle_request`
- `anyio.from_thread.BlockingPortal.call`
- `asyncio.base_events._run_once`

Top stdlib / C-backed entries included:

- `_contextvars.Context.run`
- `select.epoll.poll`
- `_socket.socket.recv` / `send`
- `builtins.isinstance`
- `pydantic_core.SchemaValidator.validate_python`

`profiling.sampling --native` adds one important nuance: a large share
of sampled wall time sits in `threading.Condition.wait` inside the
portal handoff. That means this harness is excellent for framework and
stdlib request plumbing, but it also includes real in-process client /
thread synchronization overhead.

### Celery

For practical iterative profiling, eager mode is the default. Its first
`cProfile` pass was dominated by:

- `celery.app.task.Task.delay`
- `celery.app.task.Task.apply_async`
- `celery.app.task.Task.apply`
- `celery.app.trace.trace_task`
- `celery.utils.saferepr.saferepr`
- `kombu.resource.Resource.acquire`

Top stdlib / C-backed entries included:

- `builtins.isinstance`
- `_abc._abc_instancecheck`
- `builtins.getattr`
- `dict.pop` / `dict.get`
- `str.join`
- `builtins.sum`

The eager-mode sampling pass confirmed that most time clusters around
Celery dispatch / apply / trace work rather than the small task body.
Worker mode is still available when you want to include the in-process
broker / worker loop, but it is much slower and better suited for short,
confirmatory runs.

### Django

The Django client + view workload gives a cleaner pure-Python web-stack
signal than the FastAPI harness because it avoids the heavy
`pydantic_core` path.

The first `cProfile` pass was dominated by C-backed builtins and stdlib
plumbing:

- `builtins.next`
- `builtins.getattr`
- `builtins.isinstance`
- `builtins.len`
- `bytes.join`
- `builtins.hasattr`
- `dict.get`

At the native CPython-symbol level, the main user-space hotspots were:

- `_PyEval_EvalFrameDefault`
- `_PyObject_Malloc` / `_PyObject_Free`
- `_Py_VectorCallInstrumentation_StackRefSteal`
- `unicodekeys_lookup_unicode`
- `_PyType_LookupStackRefAndVersion`
- `_PyObject_GenericGetAttrWithDict`
- `gc_collect_region`

That makes Django a good harness for measuring generic interpreter
overheads around iteration, attribute access, type checks, bytes/string
assembly, and allocation pressure.

### Jinja2

The Jinja2 render workload is useful when you want a package-heavy path
that is mostly Python-level templating and string shaping.

Its first `cProfile` pass was dominated by:

- `builtins.getattr`
- `str.join`
- `builtins.hasattr`
- `builtins.sum`
- `str.upper`
- `markupsafe._speedups._escape_inner`

At the native CPython-symbol level, the main user-space hotspots were:

- `_PyEval_EvalFrameDefault`
- `_PyObject_Malloc` / `_PyObject_Free`
- `_PyEval_Vector`
- `_Py_dict_lookup`
- `unicodekeys_lookup_unicode`
- `_PyType_LookupStackRefAndVersion`
- `_PyObject_GenericGetAttrWithDict`
- `_PyUnicode_JoinArray`

One caveat: because the template name is `report.html`, Jinja2 enables
HTML autoescaping and you will see `markupsafe._speedups` in the profile.
That still gives useful signal, but it is less "pure Python" than the
jsonschema workload below.

### jsonschema

The jsonschema workload is the cleanest current pure-Python package
signal in this directory.

The first `cProfile` pass was dominated by:

- `builtins.isinstance`
- `dict.get`
- `builtins.getattr`
- `dict.setdefault`
- `_abc._abc_instancecheck`
- `str.join`
- `builtins.len`
- `dict.items`
- `re.Pattern.search`

At the native CPython-symbol level, the main user-space hotspots were:

- `_PyEval_EvalFrameDefault`
- `_PyEval_Vector`
- `initialize_locals`
- `_PyEvalFramePushAndInit`
- `_PyObject_Malloc` / `_PyObject_Free`
- `_PyType_LookupStackRefAndVersion`
- `_Py_dict_lookup`
- `unicodekeys_lookup_unicode`
- `PyObject_Vectorcall`
- `dictiter_iternextitem`
- `_PyObject_GenericGetAttrWithDict`

This makes jsonschema especially useful for comparing branches that aim
to reduce overhead in ABC checks, generic attribute lookup, dict access,
or frame setup/teardown.
