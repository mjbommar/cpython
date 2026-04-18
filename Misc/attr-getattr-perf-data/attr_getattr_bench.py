from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import cached_property
import json
from pathlib import Path
import statistics
import time

import httpx
from celery import Celery
from django import forms
from django.conf import settings
from jinja2 import DictLoader, Environment, select_autoescape
from jsonschema import Draft202012Validator


if not settings.configured:
    settings.configure(
        DEBUG=False,
        SECRET_KEY="attr-getattr-perf",
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
                "OPTIONS": {"loaders": [("django.template.loaders.locmem.Loader", {})]},
            }
        ],
    )

import django

django.setup()

from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.template import engines
from django.test import Client
from django.urls import path


class InstanceRecord:
    def __init__(self) -> None:
        self.customer = "alice"
        self.qty = 3
        self.price_cents = 499
        self.region = "us-east"


class PropertyRecord:
    def __init__(self) -> None:
        self.__dict__["value"] = "shadowed"

    @property
    def value(self) -> str:
        return "property"


class OverrideRecord:
    def method(self) -> str:
        return "descriptor"


class MethodRecord:
    def render(self) -> str:
        return "ok"


class MissingRecord:
    pass


class SlotsRecord:
    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count = 9


class CachedPropertyRecord:
    def __init__(self) -> None:
        self.calls = 0

    @cached_property
    def total(self) -> int:
        self.calls += 1
        return 42


def micro_instance_attr_hit() -> None:
    obj = InstanceRecord()
    for _ in range(1_200_000):
        value = getattr(obj, "customer")
        if value != "alice":
            raise RuntimeError("bad attr")


def micro_property_hit() -> None:
    obj = PropertyRecord()
    for _ in range(900_000):
        value = getattr(obj, "value")
        if value != "property":
            raise RuntimeError("bad property")


def micro_method_lookup_hit() -> None:
    obj = MethodRecord()
    for _ in range(700_000):
        method = getattr(obj, "render")
        if method() != "ok":
            raise RuntimeError("bad method")


def micro_instance_override_non_data() -> None:
    obj = OverrideRecord()
    obj.method = 123
    for _ in range(1_200_000):
        value = getattr(obj, "method")
        if value != 123:
            raise RuntimeError("bad override")


def micro_missing_hasattr() -> None:
    obj = MissingRecord()
    for _ in range(900_000):
        if hasattr(obj, "missing"):
            raise RuntimeError("unexpected attr")


def micro_slots_hit() -> None:
    obj = SlotsRecord()
    for _ in range(1_200_000):
        value = getattr(obj, "count")
        if value != 9:
            raise RuntimeError("bad slot")


def micro_cached_property_hit() -> None:
    obj = CachedPropertyRecord()
    if getattr(obj, "total") != 42:
        raise RuntimeError("bad cached_property warmup")
    for _ in range(1_200_000):
        value = getattr(obj, "total")
        if value != 42:
            raise RuntimeError("bad cached_property")


class OrderForm(forms.Form):
    customer = forms.CharField(max_length=32)
    qty = forms.IntegerField(min_value=1, max_value=100)
    price_cents = forms.IntegerField(min_value=1)
    coupon = forms.BooleanField(required=False)
    tags = forms.CharField(max_length=128)


DJANGO_TEMPLATE = engines["django"].from_string(
    """
    <article>
      <h1>{{ customer|upper }}</h1>
      <p>Total: {{ total_cents }}</p>
      <ul>
      {% for label in labels %}
        <li>{{ label }}</li>
      {% endfor %}
      </ul>
    </article>
    """
)


def order_view(request: HttpRequest, route_order_id: int) -> HttpResponse:
    form = OrderForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest("invalid")

    cleaned = form.cleaned_data
    customer = cleaned["customer"]
    qty = cleaned["qty"]
    price_cents = cleaned["price_cents"]
    coupon = cleaned["coupon"]
    tags = [tag.strip().upper() for tag in cleaned["tags"].split(",") if tag.strip()]
    subtotal = qty * price_cents
    discount = 250 if coupon else 0
    total = subtotal - discount + route_order_id % 7
    labels = [f"{customer}:{tag}" for tag in tags]
    body = DJANGO_TEMPLATE.render(
        {
            "customer": customer,
            "labels": labels,
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "total_cents": total,
        },
        request,
    )
    return HttpResponse(body, content_type="text/html; charset=utf-8")


urlpatterns = [path("orders/<int:route_order_id>/", order_view)]


def real_django_request() -> None:
    client = Client()
    for i in range(1_800):
        payload = {
            "customer": f"user{i % 17}",
            "qty": str((i % 5) + 1),
            "price_cents": str(1200 + (i % 11)),
            "coupon": "on" if i % 9 == 0 else "",
            "tags": f"fast, path, dj{i % 7}",
        }
        response = client.post(f"/orders/{i % 1000}/", data=payload)
        if response.status_code != 200 or b"<article>" not in response.content:
            raise RuntimeError("bad django response")


JINJA_ENV = Environment(
    loader=DictLoader(
        {
            "report.html": """
            <section>
            {% for order in orders %}
              <article>
                <h2>{{ order.owner|upper }}</h2>
                <p>{{ order.total_cents }}</p>
                <ul>
                {% for item in order["items"] %}
                  <li>{{ item.sku }}={{ item.qty * item.unit_price_cents }}</li>
                {% endfor %}
                </ul>
              </article>
            {% endfor %}
            </section>
            """
        }
    ),
    autoescape=select_autoescape(default_for_string=False),
)
JINJA_TEMPLATE = JINJA_ENV.get_template("report.html")


@dataclass
class Item:
    sku: str
    qty: int
    unit_price_cents: int


@dataclass
class Order:
    owner: str
    items: list[Item]
    total_cents: int


def real_jinja2_render() -> None:
    for i in range(3_000):
        orders = []
        for j in range(4):
            items = [
                Item("A100", (i + j) % 4 + 1, 299),
                Item("B200", 2, 499),
                Item("C300", 1, 1299),
            ]
            total = sum(item.qty * item.unit_price_cents for item in items)
            orders.append(Order(owner=f"user{(i + j) % 13}", items=items, total_cents=total))
        rendered = JINJA_TEMPLATE.render(orders=orders)
        if "<section>" not in rendered:
            raise RuntimeError("bad jinja2 render")


JSONSCHEMA_SCHEMA = {
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
JSONSCHEMA_VALIDATOR = Draft202012Validator(JSONSCHEMA_SCHEMA)


def real_jsonschema_validate() -> None:
    for i in range(2_500):
        instance = {
            "order_id": i,
            "submitted_at": f"2026-04-18T14:{i % 60:02d}:12",
            "customer": f"user{i % 17}",
            "tags": ["priority", f"region-{i % 7}"],
            "lines": [
                {"sku": "A100", "qty": (i % 4) + 1, "unit_price_cents": 299},
                {"sku": "B200", "qty": 2, "unit_price_cents": 499},
                {"sku": "C300", "qty": 1, "unit_price_cents": 1299},
            ],
        }
        JSONSCHEMA_VALIDATOR.validate(instance)


CELERY_APP = Celery("attr_getattr_perf", broker="memory://localhost/", backend="cache+memory://")
CELERY_APP.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=True,
    task_eager_propagates=True,
    task_store_eager_result=False,
)


@CELERY_APP.task(name="attr_getattr_perf.process_order")
def process_order(order: dict[str, object]) -> dict[str, object]:
    lines = order["lines"]  # type: ignore[index]
    subtotal = sum(line["qty"] * line["unit_price_cents"] for line in lines)
    tags = sorted({tag.upper() for tag in order["tags"]})  # type: ignore[index]
    return {
        "order_id": order["order_id"],
        "subtotal_cents": subtotal,
        "tag_count": len(tags),
        "tags": tags,
    }


def real_celery_eager() -> None:
    for i in range(2_500):
        order = {
            "order_id": i,
            "submitted_at": f"2026-04-18T14:{i % 60:02d}:12",
            "tags": ["priority", "bulk", f"region-{i % 5}"],
            "lines": [
                {"sku": "A100", "qty": (i % 4) + 1, "unit_price_cents": 299},
                {"sku": "B200", "qty": 2, "unit_price_cents": 499},
                {"sku": "C300", "qty": 1, "unit_price_cents": 1299},
            ],
        }
        result = process_order.delay(order).get(timeout=10, interval=0.001)
        if "subtotal_cents" not in result:
            raise RuntimeError("bad celery result")


def real_httpx_request_data() -> None:
    payload = {
        "customer": "alice",
        "tags": ["priority", "bulk", "blue"],
        "lines": [{"sku": "A100", "qty": 2, "unit_price_cents": 299}],
    }
    for _ in range(30_000):
        request = httpx.Request(
            "POST",
            "https://example.invalid/upload",
            data={"customer": payload["customer"], "tag": payload["tags"][0]},
            files={"manifest": ("lines.json", json.dumps(payload["lines"]))},
        )
        body = request.read()
        if not body:
            raise RuntimeError("empty request body")


WORKLOADS = {
    "M1_instance_attr_hit": micro_instance_attr_hit,
    "M2_property_hit": micro_property_hit,
    "M3_method_lookup_hit": micro_method_lookup_hit,
    "M4_instance_override_non_data": micro_instance_override_non_data,
    "M5_missing_hasattr": micro_missing_hasattr,
    "M6_slots_hit": micro_slots_hit,
    "M7_cached_property_hit": micro_cached_property_hit,
    "R1_django_request": real_django_request,
    "R2_jinja2_render": real_jinja2_render,
    "R3_jsonschema_validate": real_jsonschema_validate,
    "R4_celery_eager": real_celery_eager,
    "R5_httpx_request_data": real_httpx_request_data,
}


def trimmed_mean(values: list[float]) -> float:
    ordered = sorted(values)
    if len(ordered) > 4:
        ordered = ordered[1:-1]
    return statistics.mean(ordered)


def run_benchmark(selected: list[str]) -> dict[str, object]:
    results = {}
    for name in selected:
        fn = WORKLOADS[name]
        samples = []
        for _ in range(9):
            t0 = time.perf_counter()
            fn()
            samples.append(time.perf_counter() - t0)
        results[name] = {
            "samples_s": samples,
            "trimmed_mean_s": trimmed_mean(samples),
            "min_s": min(samples),
            "max_s": max(samples),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workload", action="append", dest="workloads")
    args = parser.parse_args()

    selected = args.workloads or list(WORKLOADS)
    data = {
        "label": args.label,
        "python": f"executable={Path(__import__('sys').executable)}\nversion={__import__('sys').version}\ncwd={Path.cwd()}",
        "workloads": run_benchmark(selected),
    }
    out = Path(args.output)
    out.write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
