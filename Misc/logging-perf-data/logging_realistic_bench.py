"""
Realistic logging benchmark modeled on FastAPI / Starlette / uvicorn
production patterns.

Scenarios:

  R1: "Quiet request" — root INFO, handlers attached at root. Per request
      we emit one access-log line and a couple of app-level INFO lines;
      many DEBUG calls are filtered out.  This matches production web
      apps with verbosity set to INFO or WARNING.

  R2: "Verbose request" — root DEBUG, everything emits. Matches a dev-mode
      or debug-level deploy.

  R3: "Deep hierarchy + filtered" — 8-level deep logger name, root at
      WARNING; all DEBUG/INFO filtered out. Measures pure overhead of
      isEnabledFor when the answer is "no".

  R4: "Access-log-only" — Simulates uvicorn's access log: one emission
      per request through a dedicated logger with a dedicated handler
      and a structured format string.

The handler writes to a /dev/null-like BytesIO sink so we measure
CPU, not I/O.
"""
import io
import logging
import statistics
import sys
import time
import timeit


FORMAT = '%(asctime)s %(levelname)s %(name)s:%(lineno)d %(threadName)s - %(message)s'
# "uvicorn-style" access log format
ACCESS_FORMAT = '%(asctime)s - %(levelname)s - %(client)s - "%(method)s %(path)s HTTP/1.1" %(status)s'


def _reset():
    """Reset logging state between scenarios."""
    logging.shutdown()
    logging.Logger.manager.loggerDict.clear()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


def _make_null_handler(fmt=FORMAT):
    """A StreamHandler writing to an in-memory byte sink; measures CPU only."""
    buf = io.BytesIO()
    text = io.TextIOWrapper(buf, write_through=True)
    h = logging.StreamHandler(stream=text)
    h.setFormatter(logging.Formatter(fmt))
    return h, buf


# ---------- R1: Quiet request (INFO root) ----------
def setup_R1():
    _reset()
    root = logging.getLogger()
    h, _ = _make_null_handler()
    root.addHandler(h)
    root.setLevel(logging.INFO)
    # Fastapi-style nesting
    return {
        'api':    logging.getLogger('myapp.api'),
        'routes': logging.getLogger('myapp.api.routes.users'),
        'db':     logging.getLogger('myapp.db.conn'),
    }

def R1_run(loggers, n):
    """Per iteration: 2 filtered DEBUGs + 2 emitted INFOs — typical request."""
    routes = loggers['routes']; db = loggers['db']; api = loggers['api']
    for i in range(n):
        routes.debug("route match %s", i)                 # filtered
        db.debug("opening conn %s", i)                    # filtered
        routes.info("GET /users/%d -> 200", i)            # emitted
        api.info("request %d served in %dms", i, 1)       # emitted


# ---------- R2: Verbose (DEBUG root) ----------
def setup_R2():
    _reset()
    root = logging.getLogger()
    h, _ = _make_null_handler()
    root.addHandler(h)
    root.setLevel(logging.DEBUG)
    return {
        'routes': logging.getLogger('myapp.api.routes.users'),
        'db':     logging.getLogger('myapp.db.conn'),
    }

def R2_run(loggers, n):
    routes = loggers['routes']; db = loggers['db']
    for i in range(n):
        routes.debug("debug %s", i)
        db.debug("conn %s", i)
        routes.info("info %s", i)


# ---------- R3: Deep hierarchy, all filtered (WARNING root) ----------
def setup_R3():
    _reset()
    root = logging.getLogger()
    h, _ = _make_null_handler()
    root.addHandler(h)
    root.setLevel(logging.WARNING)
    # 8 levels deep — matches microservice + instrumented library stack
    deep = logging.getLogger('a.b.c.d.e.f.g.h')
    return {'deep': deep}

def R3_run(loggers, n):
    deep = loggers['deep']
    for _ in range(n):
        deep.debug("filtered")
        deep.info("filtered")


# ---------- R4: Access-log-only (uvicorn-style) ----------
def setup_R4():
    _reset()
    root = logging.getLogger()
    root.setLevel(logging.WARNING)  # silence app
    access = logging.getLogger('uvicorn.access')
    h, _ = _make_null_handler(ACCESS_FORMAT)
    access.addHandler(h)
    access.setLevel(logging.INFO)
    access.propagate = False
    return {'access': access}

def R4_run(loggers, n):
    access = loggers['access']
    extra = {'client': '127.0.0.1', 'method': 'GET',
             'path': '/users/42', 'status': 200}
    for _ in range(n):
        access.info('', extra=extra)


# ---------- harness ----------
SCENARIOS = [
    ('R1_quiet_request',   setup_R1, R1_run, 20_000),
    ('R2_verbose_request', setup_R2, R2_run, 20_000),
    ('R3_deep_filtered',   setup_R3, R3_run, 50_000),
    ('R4_access_log_only', setup_R4, R4_run, 20_000),
]


def run(name, setup, body, n, repeat=7):
    loggers = setup()
    runs = timeit.repeat(lambda: body(loggers, n), number=1, repeat=repeat)
    runs.sort()
    # trim hi/lo
    trimmed = runs[1:-1]
    return {
        'n': n,
        'runs': runs,
        'min': min(runs),
        'median': statistics.median(runs),
        'trimmed_mean': statistics.mean(trimmed),
    }


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else 'bench'
    print(f"\n== {label} ==")
    results = {}
    for name, setup, body, n in SCENARIOS:
        r = run(name, setup, body, n)
        results[name] = r
        per_call = r['trimmed_mean'] * 1e6 / n
        print(f"  {name:25s} n={n:6d}  trimmed_mean={r['trimmed_mean']:.4f}s"
              f"  min={r['min']:.4f}s  per_call={per_call:.2f}us")
    # Dump raw JSON for later comparison
    import json
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        with open(out, 'w') as f:
            json.dump(results, f, indent=2)
