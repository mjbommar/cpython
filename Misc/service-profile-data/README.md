# Service Profiling Harnesses

Reusable service-style workloads for profiling a CPython build on
framework-heavy paths rather than isolated micros.

Current workloads:

- `fastapi_service_workload.py`
  - in-process FastAPI app
  - request parsing, dependency injection, Pydantic validation,
    response-model serialization, Starlette/httpx test transport
- `celery_service_workload.py`
  - Celery app using `memory://` broker and `cache+memory://` backend
  - default mode uses eager execution for fast iterative profiling
  - optional worker mode starts a real in-process worker with
    `pool="solo"`
  - exercises task dispatch, tracing, Kombu JSON serialization, and
    result retrieval without requiring Redis or RabbitMQ
- `service_cprofile.py`
  - wraps either workload with `cProfile`
  - defaults to stdlib-only and builtins/C-backed hotspots
  - optional `--show-overall` includes framework wrappers too

## Dependencies

These scripts assume the interpreter under test can import:

- `fastapi`
- `httpx`
- `celery`
- `cffi`

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
