"""
End-to-end-ish Starlette benchmark: drive a request handler in-process
using Starlette's TestClient (no network, no uvicorn), measure wall time
with logging configured the way a production FastAPI/Starlette app
typically configures it.

Two configurations:
    quiet:   root level INFO, per-request handler emits 2 logs (one
             access-log-ish, one app-level)
    verbose: root level DEBUG, handler emits 5 logs including DEBUG
"""
import io
import logging
import sys
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


access_logger = logging.getLogger('myapp.access')
db_logger = logging.getLogger('myapp.db.conn')
route_logger = logging.getLogger('myapp.api.routes.users')


def setup_logging(level):
    """Install handlers in the realistic shape for this run."""
    # Reset
    logging.shutdown()
    logging.Logger.manager.loggerDict.clear()
    root = logging.getLogger()
    root.handlers.clear()

    # Sink: in-memory byte writer so we measure CPU, not disk
    buf = io.BytesIO()
    h = logging.StreamHandler(
        stream=io.TextIOWrapper(buf, write_through=True, encoding='utf-8'))
    h.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s:%(lineno)d %(threadName)s - %(message)s'
    ))
    root.addHandler(h)
    root.setLevel(level)
    return buf


def users_handler(request: Request):
    user_id = request.path_params['user_id']
    route_logger.debug("matched users route user_id=%s", user_id)
    db_logger.debug("fetching user %s from db", user_id)
    # pretend work
    data = {"id": user_id, "name": f"user-{user_id}", "role": "member"}
    db_logger.info("fetched user %s", user_id)
    access_logger.info("GET /users/%s -> 200", user_id)
    return JSONResponse(data)


app = Starlette(routes=[Route("/users/{user_id}", users_handler)])


def run_n_requests(client: TestClient, n: int) -> float:
    t0 = time.perf_counter()
    for i in range(n):
        r = client.get(f"/users/{i}")
        assert r.status_code == 200
    return time.perf_counter() - t0


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    print(f"\n== {label} ==")
    for level_name, level in [("INFO (quiet)", logging.INFO),
                              ("DEBUG (verbose)", logging.DEBUG)]:
        setup_logging(level)
        with TestClient(app) as client:
            # Warmup
            run_n_requests(client, 200)
            # Measure
            ns = [run_n_requests(client, 2_000) for _ in range(5)]
            ns.sort()
            trimmed = ns[1:-1]
            mean = sum(trimmed) / len(trimmed)
            print(f"  {level_name:22s}  trimmed_mean={mean:.4f}s"
                  f"  min={min(ns):.4f}s  per_req={mean/2000*1e6:.1f}us")
