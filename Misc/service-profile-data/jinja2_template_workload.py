"""
Jinja2 template-render profiling workload.

Designed to exercise:
- pure-Python template rendering
- dict and attribute lookups
- string joins and formatting
- loop-heavy context traversal
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

from jinja2 import DictLoader, Environment, select_autoescape


ENV = Environment(
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
TEMPLATE = ENV.get_template("report.html")


@dataclass
class Jinja2Workload:
    def warmup(self, n: int) -> None:
        self.run_iterations(n)

    def run_iterations(self, n: int) -> None:
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
            rendered = TEMPLATE.render(orders=orders)
            if "<section>" not in rendered:
                raise RuntimeError("rendered output missing expected marker")

    def close(self) -> None:
        return None


def create_workload() -> Jinja2Workload:
    return Jinja2Workload()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=6000)
    parser.add_argument("--warmup", type=int, default=300)
    args = parser.parse_args()

    workload = create_workload()
    try:
        workload.warmup(args.warmup)
        t0 = time.perf_counter()
        workload.run_iterations(args.iterations)
        elapsed = time.perf_counter() - t0
    finally:
        workload.close()
    per_render = elapsed * 1e6 / args.iterations
    print(
        f"jinja2 iterations={args.iterations} elapsed={elapsed:.4f}s "
        f"per_render={per_render:.2f}us"
    )


if __name__ == "__main__":
    main()
