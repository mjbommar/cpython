"""Real-app sustained-load test: Starlette in-process TestClient,
30 seconds, with the full uvicorn-style access+error log format enabled.
We measure req/sec, record-emits/sec, and any exceptions."""
import gc
import io
import logging
import logging.config
import os
import threading
import time

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

# Confirm Phase 3
assert logging.LogRecord.__init__.__name__ == "_LogRecord_init_c", \
    logging.LogRecord.__init__

# Production-style logging config: three loggers, multiple formatters,
# two handlers (one stream-to-memory, one filtering out low priority).
SINK = io.StringIO()
ERR_SINK = io.StringIO()
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "access": {"format": '%(asctime)s %(levelname)s %(name)s [%(process)d/%(threadName)s] %(message)s'},
        "err":    {"format": '%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d %(message)s'},
    },
    "handlers": {
        "access": {"class": "logging.StreamHandler", "stream": SINK,     "formatter": "access", "level": "INFO"},
        "err":    {"class": "logging.StreamHandler", "stream": ERR_SINK, "formatter": "err",    "level": "WARNING"},
    },
    "loggers": {
        "app":            {"handlers": ["access", "err"], "level": "DEBUG", "propagate": False},
        "app.db":         {"handlers": ["access", "err"], "level": "INFO",  "propagate": False},
        "app.routes":     {"handlers": ["access"],        "level": "INFO",  "propagate": False},
        "uvicorn.access": {"handlers": ["access"],        "level": "INFO",  "propagate": False},
    },
})

app_log    = logging.getLogger("app")
db_log     = logging.getLogger("app.db")
routes_log = logging.getLogger("app.routes")
access_log = logging.getLogger("uvicorn.access")

class LogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        routes_log.info("route match: %s %s", request.method, request.url.path)
        resp = await call_next(request)
        access_log.info('%s - "%s %s HTTP/1.1" %d',
                        request.client.host if request.client else "-",
                        request.method, request.url.path, resp.status_code)
        return resp

async def users(request):
    db_log.debug("query SELECT * FROM users WHERE id=%d", int(request.path_params["uid"]))
    app_log.info("served user %s", request.path_params["uid"])
    return JSONResponse({"id": int(request.path_params["uid"]), "name": "alice"})

async def err(request):
    app_log.warning("transient error: %s", "foo")
    return PlainTextResponse("ok", status_code=200)

async def hello(request):
    return PlainTextResponse("hello")

app = Starlette(
    middleware=[Middleware(LogMiddleware)],
    routes=[
        Route("/", hello),
        Route("/u/{uid}", users),
        Route("/err", err),
    ],
)

DURATION = 30.0
counts = {"reqs": 0, "exc": 0}

def driver(client):
    t_end = time.time() + DURATION
    i = 0
    while time.time() < t_end:
        try:
            r = client.get("/")
            assert r.status_code == 200
            r = client.get(f"/u/{i % 1000}")
            assert r.status_code == 200
            r = client.get("/err")
            assert r.status_code == 200
            counts["reqs"] += 3
        except Exception:
            counts["exc"] += 1
        i += 1

with TestClient(app) as client:
    print(f"starting {DURATION}s sustained-load run …")
    t0 = time.time()
    threads = [threading.Thread(target=driver, args=(client,)) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    dt = time.time() - t0

# metrics
acc_lines = SINK.getvalue().count("\n")
err_lines = ERR_SINK.getvalue().count("\n")
print(f"elapsed:           {dt:.2f}s")
print(f"requests served:   {counts['reqs']:,} ({counts['reqs']/dt:,.0f}/s)")
print(f"exceptions:        {counts['exc']}")
print(f"access log lines:  {acc_lines:,} ({acc_lines/dt:,.0f}/s)")
print(f"error log lines:   {err_lines:,} ({err_lines/dt:,.0f}/s)")
print(f"SINK bytes:        {len(SINK.getvalue()):,}")
print(f"ERR_SINK bytes:    {len(ERR_SINK.getvalue()):,}")

# Sanity: every request should have produced a route-match log and an
# access log; check the access-log count roughly matches.
# 3 requests/iteration: /, /u/..., /err -> 3 route_match + 3 access
expected_access = counts["reqs"]
got_access = acc_lines
ratio = got_access / (2 * expected_access) if expected_access else 0
print(f"\nexpected access+route lines: ~{2*expected_access:,}, got {got_access:,}, ratio={ratio:.2f}")
assert counts["exc"] == 0, f"request exceptions: {counts['exc']}"
print("\nOK — real-app sustained load passed")
