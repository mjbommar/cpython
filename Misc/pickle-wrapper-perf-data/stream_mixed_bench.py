#!/usr/bin/env python3

from __future__ import annotations

import argparse
import io
import json
import pickle
import statistics
import time


OBJS = [
    None,
    True,
    123456,
    "alpha-beta-gamma",
    list(range(20)),
    {"k": list(range(8)), "name": "user", "flag": False},
    tuple(range(10)),
    [{"id": i, "vals": list(range(i, i + 4))} for i in range(6)],
]


def trimmed_mean(samples: list[float]) -> float:
    if len(samples) <= 2:
        return statistics.mean(samples)
    ordered = sorted(samples)
    return statistics.mean(ordered[1:-1])


def bench(fn, *, samples: int = 7) -> dict[str, float | list[float]]:
    runs = []
    fn()
    for _ in range(samples):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return {
        "runs": runs,
        "median": statistics.median(runs),
        "trimmed_mean": trimmed_mean(runs),
    }


def dump_stream(count: int) -> None:
    bio = io.BytesIO()
    pickler = pickle.Pickler(bio, protocol=5)
    for _ in range(count):
        bio.seek(0)
        bio.truncate(0)
        pickler.clear_memo()
        for obj in OBJS:
            pickler.dump(obj)


def load_stream(count: int) -> None:
    bio = io.BytesIO()
    pickler = pickle.Pickler(bio, protocol=5)
    for obj in OBJS:
        pickler.dump(obj)
    payload = bio.getvalue() * count
    unpickler = pickle.Unpickler(io.BytesIO(payload))
    for _ in range(count * len(OBJS)):
        unpickler.load()


def roundtrip_stream(count: int) -> None:
    for _ in range(count):
        bio = io.BytesIO()
        pickler = pickle.Pickler(bio, protocol=5)
        for obj in OBJS:
            pickler.dump(obj)
        payload = bio.getvalue()
        unpickler = pickle.Unpickler(io.BytesIO(payload))
        for _ in OBJS:
            unpickler.load()


SCENARIOS = [
    ("B1_dump_stream_mixed_exact", lambda: dump_stream(20_000), 20_000),
    ("B2_load_stream_mixed_exact", lambda: load_stream(20_000), 20_000),
    ("B3_roundtrip_stream_mixed_exact", lambda: roundtrip_stream(8_000), 8_000),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--output", type=str)
    args = parser.parse_args()

    results = {}
    for name, fn, count in SCENARIOS:
        result = bench(fn, samples=args.samples)
        per_iter_ns = result["trimmed_mean"] * 1e9 / count
        print(
            f"{name:30s} count={count:7d} "
            f"trimmed_mean={result['trimmed_mean']:.6f}s "
            f"per_iter={per_iter_ns:9.2f}ns"
        )
        results[name] = {"count": count, **result}

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
