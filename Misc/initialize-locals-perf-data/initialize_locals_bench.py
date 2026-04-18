from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time

from celery import Celery
from django import forms
from django.conf import settings
from jinja2 import DictLoader, Environment, select_autoescape
from jsonschema import Draft202012Validator


if not settings.configured:
    settings.configure(
        DEBUG=False,
        SECRET_KEY="init-locals-perf-secret",
        USE_I18N=False,
        USE_TZ=False,
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

from django.template import engines


def _metadata() -> str:
    import os
    import platform
    import sys

    return (
        f"executable={sys.executable}\n"
        f"version={sys.version.strip()}\n"
        f"cwd={os.getcwd()}\n"
        f"platform={platform.platform()}"
    )


def run_timer(fn, iterations: int) -> float:
    t0 = time.perf_counter()
    fn(iterations)
    return time.perf_counter() - t0


def simple4(a, b, c, d):
    return a + b + c + d


def with_defaults(a, b, c=3, d=4):
    return a + b + c + d


def with_kwonly(a, b, *, c=3, d=4):
    return a + b + c + d


def with_varargs(a, *rest):
    return a + len(rest)


def nine_args(a, b, c, d, e, f, g, h, i):
    return a + b + c + d + e + f + g + h + i


def make_closure():
    bias = 7

    def inner(a, b, c, d):
        return a + b + c + d + bias

    return inner


CLOSURE4 = make_closure()


class BoundAdder:
    def add(self, a, b, c, d):
        return a + b + c + d


BOUND = BoundAdder()


def micro_exact_positional(n: int) -> int:
    total = 0
    for i in range(n):
        total += simple4(i, 2, 3, 4)
    return total


def micro_defaults_fill(n: int) -> int:
    total = 0
    for i in range(n):
        total += with_defaults(i, 2)
    return total


def micro_keyword_call(n: int) -> int:
    total = 0
    for i in range(n):
        total += with_kwonly(i, 2, c=5, d=6)
    return total


def micro_varargs_call(n: int) -> int:
    total = 0
    for i in range(n):
        total += with_varargs(i, 1, 2, 3, 4, 5)
    return total


def micro_bound_method(n: int) -> int:
    total = 0
    for i in range(n):
        total += BOUND.add(i, 2, 3, 4)
    return total


def micro_closure_call(n: int) -> int:
    total = 0
    for i in range(n):
        total += CLOSURE4(i, 2, 3, 4)
    return total


def micro_many9_call(n: int) -> int:
    total = 0
    for i in range(n):
        total += nine_args(i, 1, 2, 3, 4, 5, 6, 7, 8)
    return total


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


def real_jinja2_render(n: int) -> None:
    for i in range(n):
        orders = []
        for j in range(4):
            items = [
                {"sku": "A100", "qty": (i + j) % 4 + 1, "unit_price_cents": 299},
                {"sku": "B200", "qty": 2, "unit_price_cents": 499},
                {"sku": "C300", "qty": 1, "unit_price_cents": 1299},
            ]
            orders.append(
                {
                    "owner": f"user{(i + j) % 13}",
                    "items": items,
                    "total_cents": sum(item["qty"] * item["unit_price_cents"] for item in items),
                }
            )
        rendered = JINJA_TEMPLATE.render(orders=orders)
        if "<section>" not in rendered:
            raise RuntimeError("jinja render missing marker")


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


def real_django_template(n: int) -> None:
    for i in range(n):
        data = {
            "customer": f"user{i % 17}",
            "qty": str((i % 5) + 1),
            "price_cents": str(1200 + (i % 11)),
            "coupon": "on" if i % 9 == 0 else "",
            "tags": f"fast, path, dj{i % 7}",
        }
        form = OrderForm(data)
        if not form.is_valid():
            raise RuntimeError("form invalid")
        cleaned = form.cleaned_data
        customer = cleaned["customer"]
        qty = cleaned["qty"]
        price_cents = cleaned["price_cents"]
        coupon = cleaned["coupon"]
        tags = [tag.strip().upper() for tag in cleaned["tags"].split(",") if tag.strip()]
        subtotal = qty * price_cents
        total = subtotal - (250 if coupon else 0) + i % 7
        body = DJANGO_TEMPLATE.render(
            {
                "customer": customer,
                "labels": [f"{customer}:{tag}" for tag in tags],
                "total_cents": total,
            }
        )
        if "<article>" not in body:
            raise RuntimeError("django render missing marker")


SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "integer"},
        "submitted_at": {"type": "string", "pattern": r"^2026-04-18T14:\d{2}:\d{2}$"},
        "customer": {"type": "string", "minLength": 3},
        "tags": {
            "type": "array",
            "items": {"type": "string", "minLength": 2},
            "minItems": 2,
        },
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
VALIDATOR = Draft202012Validator(SCHEMA)


def real_jsonschema_validate(n: int) -> None:
    for i in range(n):
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
        VALIDATOR.validate(instance)


CELERY_APP = Celery(
    "initialize_locals_perf",
    broker="memory://localhost/",
    backend="cache+memory://",
)
CELERY_APP.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=True,
    task_store_eager_result=False,
    task_eager_propagates=True,
)


@CELERY_APP.task(name="initialize_locals_perf.process_order")
def process_order(order: dict[str, object]) -> dict[str, object]:
    submitted_at = order["submitted_at"]  # type: ignore[index]
    lines = order["lines"]  # type: ignore[index]
    subtotal = sum(line["qty"] * line["unit_price_cents"] for line in lines)
    tags = sorted({tag.upper() for tag in order["tags"]})  # type: ignore[index]
    return {
        "order_id": order["order_id"],
        "submitted_at": submitted_at,
        "subtotal_cents": subtotal,
        "tag_count": len(tags),
        "tags": tags,
    }


def real_celery_eager(n: int) -> None:
    for i in range(n):
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
            raise RuntimeError("celery result missing key")


WORKLOADS = {
    "M1_exact_positional": (micro_exact_positional, 220_000),
    "M2_defaults_fill": (micro_defaults_fill, 220_000),
    "M3_keyword_call": (micro_keyword_call, 180_000),
    "M4_varargs_call": (micro_varargs_call, 180_000),
    "M5_bound_method": (micro_bound_method, 220_000),
    "M6_closure_call": (micro_closure_call, 220_000),
    "M7_many9_call": (micro_many9_call, 160_000),
    "R1_jinja2_render": (real_jinja2_render, 4_000),
    "R2_django_template": (real_django_template, 2_000),
    "R3_jsonschema_validate": (real_jsonschema_validate, 3_000),
    "R4_celery_eager": (real_celery_eager, 1_000),
}


def bench_workload(fn, iterations: int, samples: int) -> dict[str, object]:
    times = [run_timer(fn, iterations) for _ in range(samples)]
    ordered = sorted(times)
    trimmed = ordered[1:-1] if len(ordered) >= 5 else ordered
    return {
        "iterations": iterations,
        "samples_s": times,
        "trimmed_mean_s": sum(trimmed) / len(trimmed),
        "min_s": min(times),
        "max_s": max(times),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--workloads", nargs="*")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected = args.workloads or list(WORKLOADS)
    data = {"label": args.label, "python": _metadata(), "workloads": {}}
    for name in selected:
        fn, iterations = WORKLOADS[name]
        data["workloads"][name] = bench_workload(fn, iterations, args.samples)
    args.output.write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
