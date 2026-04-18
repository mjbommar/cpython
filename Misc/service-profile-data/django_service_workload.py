"""
Django service-style profiling workload.

Designed to exercise:
- URL resolving
- request object creation
- form binding and validation
- Django template rendering
- response assembly
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

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


class OrderForm(forms.Form):
    customer = forms.CharField(max_length=32)
    qty = forms.IntegerField(min_value=1, max_value=100)
    price_cents = forms.IntegerField(min_value=1)
    coupon = forms.BooleanField(required=False)
    tags = forms.CharField(max_length=128)


TEMPLATE = engines["django"].from_string(
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
    body = TEMPLATE.render(
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


urlpatterns = [
    path("orders/<int:route_order_id>/", order_view),
]


@dataclass
class DjangoWorkload:
    client: Client

    def warmup(self, n: int) -> None:
        self.run_iterations(n)

    def run_iterations(self, n: int) -> None:
        for i in range(n):
            payload = {
                "customer": f"user{i % 17}",
                "qty": str((i % 5) + 1),
                "price_cents": str(1200 + (i % 11)),
                "coupon": "on" if i % 9 == 0 else "",
                "tags": f"fast, path, dj{i % 7}",
            }
            response = self.client.post(f"/orders/{i % 1000}/", data=payload)
            if response.status_code != 200:
                raise RuntimeError(f"unexpected status: {response.status_code}")
            if b"<article>" not in response.content:
                raise RuntimeError("response body missing expected marker")

    def close(self) -> None:
        return None


def create_workload() -> DjangoWorkload:
    return DjangoWorkload(client=Client())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--warmup", type=int, default=200)
    args = parser.parse_args()

    workload = create_workload()
    try:
        workload.warmup(args.warmup)
        t0 = time.perf_counter()
        workload.run_iterations(args.iterations)
        elapsed = time.perf_counter() - t0
    finally:
        workload.close()
    per_request = elapsed * 1e6 / args.iterations
    print(
        f"django iterations={args.iterations} elapsed={elapsed:.4f}s "
        f"per_request={per_request:.2f}us"
    )


if __name__ == "__main__":
    main()
