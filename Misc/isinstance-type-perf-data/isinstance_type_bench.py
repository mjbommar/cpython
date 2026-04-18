#!/usr/bin/env python3
from __future__ import annotations

import abc
import argparse
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import gc
import importlib.util
import inspect
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class SupportsClose(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class HasX(Protocol):
    x: int


class Closable:
    def close(self) -> None:
        return None


class HasInstanceX:
    def __init__(self) -> None:
        self.x = 1


class NoX:
    pass


class MappingProxy:
    @property
    def __class__(self):
        return dict


class AwaitableBox:
    def __await__(self):
        if False:
            yield None
        return 1


def trimmed_mean(values: list[float]) -> float:
    values = sorted(values)
    if len(values) > 4:
        values = values[1:-1]
    return statistics.mean(values)


def time_callable(fn, repeats: int = 9) -> dict[str, object]:
    samples = []
    gc_state = gc.isenabled()
    gc.disable()
    try:
        for _ in range(repeats):
            start = time.perf_counter()
            fn()
            samples.append(time.perf_counter() - start)
    finally:
        if gc_state:
            gc.enable()
    return {
        "samples_s": samples,
        "trimmed_mean_s": trimmed_mean(samples),
        "min_s": min(samples),
        "max_s": max(samples),
    }


def load_source_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def m1_mapping_positive_cache() -> None:
    obj = {"a": 1}
    for _ in range(800_000):
        isinstance(obj, Mapping)


def m2_mapping_negative_cache() -> None:
    obj = object()
    for _ in range(800_000):
        isinstance(obj, Mapping)


def m3_proxy_fake_class_positive() -> None:
    obj = MappingProxy()
    for _ in range(200_000):
        isinstance(obj, Mapping)


def m4_protocol_class_method_positive() -> None:
    obj = Closable()
    for _ in range(300_000):
        isinstance(obj, SupportsClose)


def m5_protocol_instance_attr_positive() -> None:
    obj = HasInstanceX()
    for _ in range(300_000):
        isinstance(obj, HasX)


def m6_protocol_negative() -> None:
    obj = NoX()
    for _ in range(300_000):
        isinstance(obj, HasX)


def r1_inspect_isawaitable() -> None:
    obj = AwaitableBox()
    for _ in range(500_000):
        inspect.isawaitable(obj)


def r2_httpx_encode_request_data() -> None:
    from httpx._content import encode_request

    data = {"alpha": "1", "beta": "2", "gamma": "3"}
    for _ in range(120_000):
        encode_request(data=data)


def r3_typeguard_check_mapping() -> None:
    from typeguard import CollectionCheckStrategy, TypeCheckConfiguration, TypeCheckMemo
    from typeguard._checkers import check_mapping

    value = {str(i): [i, i + 1, i + 2] for i in range(30)}
    memo = TypeCheckMemo(
        globals(),
        locals(),
        config=TypeCheckConfiguration(
            collection_check_strategy=CollectionCheckStrategy.ALL_ITEMS
        ),
    )
    args = (str, list[int])
    for _ in range(6_000):
        check_mapping(value, dict, args, memo)


def r4_jsonschema_equal() -> None:
    from jsonschema._utils import equal

    left = {
        "users": [{"id": i, "roles": ["reader", "writer"], "flags": [True, False]} for i in range(40)],
        "meta": {"page": 1, "count": 40},
    }
    right = {
        "users": [{"id": i, "roles": ["reader", "writer"], "flags": [True, False]} for i in range(40)],
        "meta": {"page": 1, "count": 40},
    }
    for _ in range(4_000):
        equal(left, right)


def r5_jsonschema_validator_protocol() -> None:
    from jsonschema.protocols import Validator

    attrs = {
        name: (
            {}
            if name in {"META_SCHEMA", "VALIDATORS", "TYPE_CHECKER", "FORMAT_CHECKER", "schema"}
            else (lambda *args, **kwargs: None)
        )
        for name in Validator.__protocol_attrs__
    }
    validator = type("BenchValidator", (), attrs)()
    for _ in range(200_000):
        isinstance(validator, Validator)


def r6_jsonschema_validate() -> None:
    from jsonschema import Draft202012Validator

    schema = {
        "type": "object",
        "properties": {
            "order_id": {"type": "integer"},
            "submitted_at": {"type": "string", "pattern": r"^2026-04-18T14:\d{2}:\d{2}$"},
            "customer": {"type": "string", "minLength": 3},
            "tags": {"type": "array", "items": {"type": "string", "minLength": 2}, "minItems": 2},
            "lines": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "sku": {"type": "string"},
                        "qty": {"type": "integer", "minimum": 1},
                        "unit_price_cents": {"type": "integer", "minimum": 1},
                    },
                    "required": ["sku", "qty", "unit_price_cents"],
                    "additionalProperties": False,
                },
                "minItems": 2,
            },
        },
        "required": ["order_id", "submitted_at", "customer", "tags", "lines"],
        "additionalProperties": False,
    }
    validator = Draft202012Validator(schema)
    for i in range(8_000):
        instance = {
            "order_id": i,
            "submitted_at": f"2026-04-18T14:{i % 60:02d}:12",
            "customer": f"user{i % 17}",
            "tags": ["priority", f"region-{i % 7}"],
            "lines": [
                {"sku": "A100", "qty": (i % 4) + 1, "unit_price_cents": 299},
                {"sku": "B200", "qty": 2, "unit_price_cents": 499},
            ],
        }
        validator.validate(instance)


_django_ready = False
_django_client = None


def ensure_django_client():
    global _django_ready, _django_client
    if _django_ready:
        return _django_client

    from django import forms
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            SECRET_KEY="service-profile-secret",
            ROOT_URLCONF=__name__,
            ALLOWED_HOSTS=["testserver"],
            USE_I18N=False,
            USE_TZ=False,
            MIDDLEWARE=[],
            INSTALLED_APPS=[],
            TEMPLATES=[
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "APP_DIRS": False,
                    "OPTIONS": {
                        "loaders": [("django.template.loaders.locmem.Loader", {})],
                    },
                }
            ],
        )

    import django

    django.setup()

    from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
    from django.template import engines
    from django.test import Client
    from django.urls import clear_url_caches, path

    class OrderForm(forms.Form):
        customer = forms.CharField(max_length=32)
        qty = forms.IntegerField(min_value=1, max_value=100)
        price_cents = forms.IntegerField(min_value=1)
        coupon = forms.BooleanField(required=False)
        tags = forms.CharField(max_length=128)

    template = engines["django"].from_string(
        """
        <article>
          <h1>{{ customer|upper }}</h1>
          <p>Total: {{ total_cents }}</p>
        </article>
        """
    )

    def order_view(request: HttpRequest, route_order_id: int) -> HttpResponse:
        form = OrderForm(request.POST)
        if not form.is_valid():
            return HttpResponseBadRequest("invalid")
        cleaned = form.cleaned_data
        total = cleaned["qty"] * cleaned["price_cents"] - (250 if cleaned["coupon"] else 0)
        body = template.render(
            {"customer": cleaned["customer"], "total_cents": total + route_order_id % 7},
            request,
        )
        return HttpResponse(body, content_type="text/html; charset=utf-8")

    globals()["urlpatterns"] = [path("orders/<int:route_order_id>/", order_view)]
    clear_url_caches()
    _django_client = Client()
    _django_ready = True
    return _django_client


def r7_django_request() -> None:
    client = ensure_django_client()
    for i in range(2_000):
        response = client.post(
            f"/orders/{i % 1000}/",
            data={
                "customer": f"user{i % 17}",
                "qty": str((i % 5) + 1),
                "price_cents": str(1200 + (i % 11)),
                "coupon": "on" if i % 9 == 0 else "",
                "tags": f"fast, path, dj{i % 7}",
            },
        )
        if response.status_code != 200:
            raise RuntimeError(f"unexpected status: {response.status_code}")


_celery_app = None


def ensure_celery_app():
    global _celery_app
    if _celery_app is not None:
        return _celery_app

    from celery import Celery

    app = Celery("bench_instancecheck", broker="memory://localhost/", backend="cache+memory://")
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_always_eager=True,
        task_eager_propagates=True,
        task_store_eager_result=False,
    )

    @app.task(name="bench_instancecheck.process_order")
    def process_order(order: dict[str, object]) -> dict[str, object]:
        submitted_at = datetime.fromisoformat(order["submitted_at"])  # type: ignore[index]
        lines = order["lines"]  # type: ignore[index]
        subtotal = sum(line["qty"] * line["unit_price_cents"] for line in lines)
        tags = sorted({tag.upper() for tag in order["tags"]})  # type: ignore[index]
        return {
            "order_id": order["order_id"],
            "submitted_hour": submitted_at.hour,
            "subtotal_cents": subtotal,
            "tag_count": len(tags),
        }

    _celery_app = app
    return _celery_app


def r8_celery_eager() -> None:
    app = ensure_celery_app()
    task = app.tasks["bench_instancecheck.process_order"]
    for i in range(6_000):
        result = task.delay(
            {
                "order_id": i,
                "submitted_at": f"2026-04-18T14:{i % 60:02d}:12",
                "tags": ["priority", "bulk", f"region-{i % 5}"],
                "lines": [
                    {"sku": "A100", "qty": (i % 4) + 1, "unit_price_cents": 299},
                    {"sku": "B200", "qty": 2, "unit_price_cents": 499},
                ],
            }
        ).get(timeout=10, interval=0.001)
        if "subtotal_cents" not in result:
            raise RuntimeError("task result missing subtotal")


WORKLOADS = {
    "M1_mapping_positive_cache": m1_mapping_positive_cache,
    "M2_mapping_negative_cache": m2_mapping_negative_cache,
    "M3_proxy_fake_class_positive": m3_proxy_fake_class_positive,
    "M4_protocol_class_method_positive": m4_protocol_class_method_positive,
    "M5_protocol_instance_attr_positive": m5_protocol_instance_attr_positive,
    "M6_protocol_negative": m6_protocol_negative,
    "R1_inspect_isawaitable": r1_inspect_isawaitable,
    "R2_httpx_encode_request_data": r2_httpx_encode_request_data,
    "R3_typeguard_check_mapping": r3_typeguard_check_mapping,
    "R4_jsonschema_equal": r4_jsonschema_equal,
    "R5_jsonschema_validator_protocol": r5_jsonschema_validator_protocol,
    "R6_jsonschema_validate": r6_jsonschema_validate,
    "R7_django_request": r7_django_request,
    "R8_celery_eager": r8_celery_eager,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--label", default="unspecified")
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--workload", action="append", dest="workloads", default=None)
    args = parser.parse_args()

    results = {
        "label": args.label,
        "python": inspect.cleandoc(
            f"""
            executable={sys.executable}
            version={sys.version}
            cwd={os.getcwd()}
            """
        ),
        "workloads": {},
    }
    selected = WORKLOADS
    if args.workloads:
        selected = {name: WORKLOADS[name] for name in args.workloads}

    for name, fn in selected.items():
        results["workloads"][name] = time_callable(fn, repeats=args.repeats)

    payload = json.dumps(results, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
