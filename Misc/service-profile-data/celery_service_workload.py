"""
Celery service-style profiling workload.

Default mode uses Celery eager execution for fast iterative profiling.
Worker mode starts a real in-process worker backed by memory transport so
profiling includes task dispatch, tracing, Kombu JSON serialization, and
result retrieval without needing an external broker, but it is much slower.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
import time

from celery import Celery
from celery.contrib.testing.worker import start_worker


app = Celery(
    "service_profile",
    broker="memory://localhost/",
    backend="cache+memory://",
)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_always_eager=False,
    task_store_eager_result=False,
)


@app.task(name="service_profile.process_order")
def process_order(order: dict[str, object]) -> dict[str, object]:
    submitted_at = datetime.fromisoformat(order["submitted_at"])  # type: ignore[index]
    lines = order["lines"]  # type: ignore[index]
    subtotal = sum(line["qty"] * line["unit_price_cents"] for line in lines)
    unique_tags = sorted({tag.upper() for tag in order["tags"]})  # type: ignore[index]
    return {
        "order_id": order["order_id"],
        "submitted_hour": submitted_at.hour,
        "subtotal_cents": subtotal,
        "tag_count": len(unique_tags),
        "tags": unique_tags,
    }


@dataclass
class CeleryWorkload:
    mode: str
    worker_cm: object | None

    def warmup(self, n: int) -> None:
        self.run_iterations(n)

    def run_iterations(self, n: int) -> None:
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
                raise RuntimeError("task result missing expected key")

    def close(self) -> None:
        if self.worker_cm is not None:
            self.worker_cm.__exit__(None, None, None)


def create_workload(mode: str = "eager") -> CeleryWorkload:
    if mode == "eager":
        app.conf.task_always_eager = True
        app.conf.task_eager_propagates = True
        return CeleryWorkload(mode=mode, worker_cm=None)

    app.conf.task_always_eager = False
    worker_cm = start_worker(
        app,
        pool="solo",
        concurrency=1,
        loglevel="ERROR",
        perform_ping_check=False,
    )
    worker_cm.__enter__()
    return CeleryWorkload(mode=mode, worker_cm=worker_cm)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--mode", choices=["worker", "eager"], default="eager")
    args = parser.parse_args()

    workload = create_workload(mode=args.mode)
    try:
        workload.warmup(args.warmup)
        t0 = time.perf_counter()
        workload.run_iterations(args.iterations)
        elapsed = time.perf_counter() - t0
    finally:
        workload.close()
    per_task = elapsed * 1e6 / args.iterations
    print(
        f"celery mode={args.mode} iterations={args.iterations} "
        f"elapsed={elapsed:.4f}s per_task={per_task:.2f}us"
    )


if __name__ == "__main__":
    main()
