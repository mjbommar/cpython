"""
Third-party workloads that still exercise stdlib json.

These scenarios intentionally keep the wrapper/framework layers in place
so we measure the stdlib json changes in realistic call paths:

  - httpx Request(..., json=...)
  - httpx Response(...).json()
  - Starlette JSONResponse
  - FastAPI JSONResponse(jsonable_encoder(...))
  - Flask app.json.dumps
  - Django JsonResponse
  - dataclasses_json to_json / from_json

All results are reported as microseconds per operation.
"""

from dataclasses import dataclass
import gc
import json
import statistics
import sys
import timeit

from dataclasses_json import dataclass_json
from django.conf import settings
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse as FastAPIJSONResponse
from flask import Flask
import httpx
from pydantic import BaseModel
from starlette.responses import JSONResponse as StarletteJSONResponse


if not settings.configured:
    settings.configure(
        DEFAULT_CHARSET="utf-8",
        SECRET_KEY="bench",
        ALLOWED_HOSTS=["*"],
        USE_TZ=False,
    )
import django

django.setup()

from django.http import JsonResponse


PAYLOAD = {
    "user": {"id": 42, "name": "Ana", "roles": ["admin", "editor"]},
    "ok": True,
    "count": 3,
    "pi": 3.5,
    "tags": ["x", "y"],
}
JSON_TEXT = json.dumps(PAYLOAD, separators=(",", ":"), ensure_ascii=False)
APP = Flask(__name__)


@dataclass_json
@dataclass
class User:
    id: int
    name: str
    roles: list[str]


USER = User(42, "Ana", ["admin", "editor"])
USER_JSON = USER.to_json()


class Item(BaseModel):
    id: int
    name: str
    roles: list[str]
    ok: bool


ITEM = Item(id=42, name="Ana", roles=["admin", "editor"], ok=True)


def run_httpx_request(n):
    for _ in range(n):
        httpx.Request("POST", "https://example.com", json=PAYLOAD)


def run_httpx_response(n):
    for _ in range(n):
        httpx.Response(200, text=JSON_TEXT).json()


def run_starlette(n):
    for _ in range(n):
        StarletteJSONResponse(PAYLOAD).body


def run_fastapi(n):
    for _ in range(n):
        FastAPIJSONResponse(jsonable_encoder(ITEM)).body


def run_flask(n):
    with APP.app_context():
        for _ in range(n):
            APP.json.dumps(PAYLOAD)


def run_django(n):
    for _ in range(n):
        JsonResponse(PAYLOAD).content


def run_dataclasses_json_to(n):
    for _ in range(n):
        USER.to_json()


def run_dataclasses_json_from(n):
    for _ in range(n):
        User.from_json(USER_JSON)


SCENARIOS = [
    ("httpx_request_json", run_httpx_request, 5_000),
    ("httpx_response_json", run_httpx_response, 5_000),
    ("starlette_jsonresponse", run_starlette, 5_000),
    ("fastapi_jsonresponse", run_fastapi, 3_000),
    ("flask_json_dumps", run_flask, 5_000),
    ("django_jsonresponse", run_django, 5_000),
    ("dataclasses_json_to", run_dataclasses_json_to, 3_000),
    ("dataclasses_json_from", run_dataclasses_json_from, 3_000),
]


def run(name, fn, n, repeat=7):
    gc.collect()
    runs = timeit.repeat(lambda: fn(n), number=1, repeat=repeat)
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
    for name, fn, n in SCENARIOS:
        result = run(name, fn, n)
        per_call = result["trimmed_mean"] * 1e6 / n
        print(
            f"  {name:22s} n={n:6d}  trimmed_mean={result['trimmed_mean']:.4f}s"
            f"  min={result['min']:.4f}s  per_call={per_call:.2f}us"
        )
