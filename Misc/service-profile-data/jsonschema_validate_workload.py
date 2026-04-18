"""
jsonschema validation profiling workload.

Designed to exercise:
- pure-Python schema walking
- nested dict/list traversal
- regex and format checks
- repeated isinstance / attribute checks
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import time

from jsonschema import Draft202012Validator


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


@dataclass
class JsonschemaWorkload:
    def warmup(self, n: int) -> None:
        self.run_iterations(n)

    def run_iterations(self, n: int) -> None:
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

    def close(self) -> None:
        return None


def create_workload() -> JsonschemaWorkload:
    return JsonschemaWorkload()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3000)
    parser.add_argument("--warmup", type=int, default=150)
    args = parser.parse_args()

    workload = create_workload()
    try:
        workload.warmup(args.warmup)
        t0 = time.perf_counter()
        workload.run_iterations(args.iterations)
        elapsed = time.perf_counter() - t0
    finally:
        workload.close()
    per_validate = elapsed * 1e6 / args.iterations
    print(
        f"jsonschema iterations={args.iterations} elapsed={elapsed:.4f}s "
        f"per_validate={per_validate:.2f}us"
    )


if __name__ == "__main__":
    main()
