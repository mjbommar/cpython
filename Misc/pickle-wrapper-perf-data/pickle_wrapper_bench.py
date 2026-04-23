#!/usr/bin/env python3

from __future__ import annotations

import argparse
import io
import json
import pickle
import statistics
import time
from typing import Callable


def trimmed_mean(samples: list[float]) -> float:
    if len(samples) <= 2:
        return statistics.mean(samples)
    ordered = sorted(samples)
    return statistics.mean(ordered[1:-1])


def bench(fn: Callable[[], None], *, samples: int = 9) -> dict[str, float | list[float]]:
    runs = []
    fn()
    for _ in range(samples):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return {
        "runs": runs,
        "min": min(runs),
        "median": statistics.median(runs),
        "trimmed_mean": trimmed_mean(runs),
    }


SMALL_LIST = list(range(20))
NESTED_OBJECT = [
    {
        "id": i,
        "name": f"user-{i}",
        "values": list(range(i, i + 8)),
        "meta": {"even": (i % 2) == 0, "tags": ("a", "b", "c")},
    }
    for i in range(16)
]


def dump_none_exact(count: int) -> None:
    bio = io.BytesIO()
    pickler = pickle.Pickler(bio, protocol=5)
    for _ in range(count):
        bio.seek(0)
        bio.truncate(0)
        pickler.clear_memo()
        pickler.dump(None)


def dump_small_list_exact(count: int) -> None:
    bio = io.BytesIO()
    pickler = pickle.Pickler(bio, protocol=5)
    for _ in range(count):
        bio.seek(0)
        bio.truncate(0)
        pickler.clear_memo()
        pickler.dump(SMALL_LIST)


def dump_nested_exact(count: int) -> None:
    bio = io.BytesIO()
    pickler = pickle.Pickler(bio, protocol=5)
    for _ in range(count):
        bio.seek(0)
        bio.truncate(0)
        pickler.clear_memo()
        pickler.dump(NESTED_OBJECT)


def load_repeated_exact(obj, count: int) -> None:
    payload = pickle.dumps(obj, protocol=5)
    bio = io.BytesIO(payload * count)
    unpickler = pickle.Unpickler(bio)
    for _ in range(count):
        unpickler.load()


SCENARIOS = [
    ("P1_dump_none_exact", lambda: dump_none_exact(120_000), 120_000),
    ("P2_dump_small_list_exact", lambda: dump_small_list_exact(30_000), 30_000),
    ("P3_dump_nested_exact", lambda: dump_nested_exact(4_000), 4_000),
    ("P4_load_none_exact", lambda: load_repeated_exact(None, 150_000), 150_000),
    ("P5_load_small_list_exact", lambda: load_repeated_exact(SMALL_LIST, 40_000), 40_000),
    ("P6_load_nested_exact", lambda: load_repeated_exact(NESTED_OBJECT, 5_000), 5_000),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=9)
    parser.add_argument("--output", type=str)
    args = parser.parse_args()

    results = {}
    for name, fn, count in SCENARIOS:
        result = bench(fn, samples=args.samples)
        per_iter_ns = result["trimmed_mean"] * 1e9 / count
        print(
            f"{name:24s} count={count:7d} "
            f"trimmed_mean={result['trimmed_mean']:.6f}s "
            f"per_iter={per_iter_ns:9.2f}ns"
        )
        results[name] = {"count": count, **result}

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
