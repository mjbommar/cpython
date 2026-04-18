"""
Third-party logging workloads that still exercise stdlib logging.

These scenarios keep the framework formatter / wrapper behavior but send
output to an in-memory sink so the measurement stays CPU-bound:

  - structlog stdlib wrapper
  - uvicorn.access formatter
  - Flask app.logger
  - Django ServerFormatter
  - Celery ColorFormatter

All results are reported as microseconds per emitted record.
"""

import io
import logging
import statistics
import sys
import timeit

from celery.utils.log import ColorFormatter
from django.conf import settings
from flask import Flask
import structlog
from uvicorn.logging import AccessFormatter


if not settings.configured:
    settings.configure(
        DEFAULT_CHARSET="utf-8",
        SECRET_KEY="bench",
        ALLOWED_HOSTS=["*"],
        USE_TZ=False,
    )
import django

django.setup()

from django.utils.log import ServerFormatter


FORMAT = "%(levelname)s %(name)s %(message)s"


def _reset():
    logging.shutdown()
    logging.Logger.manager.loggerDict.clear()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


def _make_handler(formatter):
    buf = io.BytesIO()
    text = io.TextIOWrapper(buf, write_through=True)
    handler = logging.StreamHandler(text)
    handler.setFormatter(formatter)
    return handler


def setup_structlog():
    _reset()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_make_handler(logging.Formatter(FORMAT)))
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.KeyValueRenderer(
                key_order=["event", "user_id", "ok"]
            ),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger("svc.api")


def run_structlog(log, n):
    for i in range(n):
        log.info("served", user_id=i, ok=True)


def setup_uvicorn():
    _reset()
    logger = logging.getLogger("uvicorn.access")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(
        _make_handler(
            AccessFormatter(
                '%(client_addr)s - "%(request_line)s" %(status_code)s',
                use_colors=False,
            )
        )
    )
    return logger


def run_uvicorn(logger, n):
    for _ in range(n):
        logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:1234",
            "GET",
            "/users/42",
            "1.1",
            200,
        )


def setup_flask():
    _reset()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_make_handler(logging.Formatter(FORMAT)))
    app = Flask(__name__)
    app.logger.handlers.clear()
    app.logger.propagate = True
    app.logger.setLevel(logging.INFO)
    return app


def run_flask(app, n):
    for i in range(n):
        app.logger.info("served %s", i)


def setup_django():
    _reset()
    logger = logging.getLogger("django.server")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(
        _make_handler(ServerFormatter("{server_time} {message}", style="{"))
    )
    return logger


def run_django(logger, n):
    for i in range(n):
        logger.info("GET /users/%s 200", i, extra={"status_code": 200})


def setup_celery():
    _reset()
    logger = logging.getLogger("celery.task")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(
        _make_handler(ColorFormatter("%(levelname)s:%(message)s", use_color=False))
    )
    return logger


def run_celery(logger, n):
    for i in range(n):
        logger.warning("task %s retry", i)


SCENARIOS = [
    ("structlog_stdlib", setup_structlog, run_structlog, 10_000),
    ("uvicorn_access", setup_uvicorn, run_uvicorn, 10_000),
    ("flask_app_logger", setup_flask, run_flask, 10_000),
    ("django_server", setup_django, run_django, 10_000),
    ("celery_color", setup_celery, run_celery, 10_000),
]


def run(name, setup, body, n, repeat=7):
    obj = setup()
    runs = timeit.repeat(lambda: body(obj, n), number=1, repeat=repeat)
    runs.sort()
    trimmed = runs[1:-1]
    return {
        "n": n,
        "runs": runs,
        "min": min(runs),
        "median": statistics.median(runs),
        "trimmed_mean": statistics.mean(trimmed),
    }


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    print(f"\n== {label} ==")
    for name, setup, body, n in SCENARIOS:
        result = run(name, setup, body, n)
        per_call = result["trimmed_mean"] * 1e6 / n
        print(
            f"  {name:22s} n={n:6d}  trimmed_mean={result['trimmed_mean']:.4f}s"
            f"  min={result['min']:.4f}s  per_call={per_call:.2f}us"
        )
