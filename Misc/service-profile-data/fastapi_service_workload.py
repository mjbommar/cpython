"""
FastAPI service-style profiling workload.

Designed to exercise:
- request body parsing
- dependency injection
- Pydantic validation
- FastAPI response-model serialization
- Starlette/httpx in-process request transport
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


class ItemIn(BaseModel):
    item_id: int
    qty: int = Field(ge=1, le=100)
    price_cents: int = Field(ge=1)
    tags: list[str]
    owner: str
    coupon: bool = False


class ItemOut(BaseModel):
    item_id: int
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    labels: list[str]


def get_multiplier() -> int:
    return 3


app = FastAPI()


@app.post("/items/{route_item_id}", response_model=ItemOut)
def create_item(
    route_item_id: int,
    item: ItemIn,
    multiplier: int = Depends(get_multiplier),
) -> ItemOut:
    subtotal = item.price_cents * item.qty
    discount = 250 if item.coupon else 0
    total = subtotal * multiplier - discount
    labels = [f"{item.owner}:{tag.upper()}" for tag in item.tags]
    return ItemOut(
        item_id=route_item_id,
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=total,
        labels=labels,
    )


@dataclass
class FastAPIWorkload:
    client: TestClient

    def warmup(self, n: int) -> None:
        self.run_iterations(n)

    def run_iterations(self, n: int) -> None:
        for i in range(n):
            payload = {
                "item_id": i,
                "qty": (i % 5) + 1,
                "price_cents": 1250 + (i % 17),
                "tags": ["fast", "path", f"t{i % 7}"],
                "owner": f"user{i % 13}",
                "coupon": (i % 11 == 0),
            }
            response = self.client.post(f"/items/{i % 1000}", json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"unexpected status: {response.status_code}")
            body = response.json()
            if "total_cents" not in body:
                raise RuntimeError("response body missing expected key")

    def close(self) -> None:
        self.client.__exit__(None, None, None)


def create_workload() -> FastAPIWorkload:
    client = TestClient(app)
    client.__enter__()
    return FastAPIWorkload(client=client)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5000)
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
    per_request = elapsed * 1e6 / args.iterations
    print(
        f"fastapi iterations={args.iterations} elapsed={elapsed:.4f}s "
        f"per_request={per_request:.2f}us"
    )


if __name__ == "__main__":
    main()
