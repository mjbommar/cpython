#!/usr/bin/env python3
"""Focused benchmark for pure-Python pickle tuple fast-path ideas."""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import pickle
import statistics
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


PY_PICKLER = pickle._Pickler

TUPLE_OF_INTS_10K = tuple(range(10_000))
TUPLE_OF_STRS_1K = tuple(f"item_{i}" for i in range(1_000))
NESTED_TUPLE = tuple((i, i + 1, i + 2) for i in range(1000))
MIXED_SCALAR_TUPLE = tuple([0, "x", 1.5, None, True] * 400)
SMALL_INT_TUPLE = (7,) * 128
INT_PAIR_TUPLE = tuple((i, i + 1) for i in range(1000))
TUPLE_OF_DICTS = tuple({"id": i, "name": f"n{i}", "val": i * 2} for i in range(500))


class Variant:
    def __init__(self, variant: str) -> None:
        self.variant = variant

    def __enter__(self):
        if self.variant != "baseline":
            install_candidate(self.variant)
        return self

    def __exit__(self, exc_type, exc, tb):
        restore_original()
        return False


def _dump(obj):
    bio = io.BytesIO()
    pickler = PY_PICKLER(bio, protocol=5)
    pickler.dump(obj)
    return bio.getvalue()


def measure(label, func, *, loops: int, repeat: int) -> dict[str, object]:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        for _ in range(loops):
            func()
        elapsed = time.perf_counter() - start
        samples.append(elapsed / loops)
    return {
        "label": label,
        "loops": loops,
        "repeat": repeat,
        "samples_ns": [round(sample * 1e9, 1) for sample in samples],
        "best_ns": round(min(samples) * 1e9, 1),
        "mean_ns": round(statistics.mean(samples) * 1e9, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "exact_int_tuples"),
        default="baseline",
    )
    parser.add_argument("--loops-small", type=int, default=3000)
    parser.add_argument("--loops-medium", type=int, default=1200)
    parser.add_argument("--loops-large", type=int, default=200)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "T1_tuple_of_ints_10k_dump": measure(
                "tuple_of_ints_10k_dump",
                lambda: _dump(TUPLE_OF_INTS_10K),
                loops=ns.loops_large,
                repeat=ns.repeat,
            ),
            "T2_tuple_of_strs_1k_dump": measure(
                "tuple_of_strs_1k_dump",
                lambda: _dump(TUPLE_OF_STRS_1K),
                loops=max(200, ns.loops_medium // 2),
                repeat=ns.repeat,
            ),
            "T3_nested_tuple_dump": measure(
                "nested_tuple_dump",
                lambda: _dump(NESTED_TUPLE),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "T4_mixed_scalar_tuple_dump": measure(
                "mixed_scalar_tuple_dump",
                lambda: _dump(MIXED_SCALAR_TUPLE),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "T5_small_int_tuple_dump": measure(
                "small_int_tuple_dump",
                lambda: _dump(SMALL_INT_TUPLE),
                loops=ns.loops_small,
                repeat=ns.repeat,
            ),
            "T6_int_pair_tuple_dump": measure(
                "int_pair_tuple_dump",
                lambda: _dump(INT_PAIR_TUPLE),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "T7_tuple_of_dicts_dump": measure(
                "tuple_of_dicts_dump",
                lambda: _dump(TUPLE_OF_DICTS),
                loops=max(150, ns.loops_medium // 2),
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "T1_tuple_of_ints_10k_dump",
        "T2_tuple_of_strs_1k_dump",
        "T3_nested_tuple_dump",
        "T4_mixed_scalar_tuple_dump",
        "T5_small_int_tuple_dump",
        "T6_int_pair_tuple_dump",
        "T7_tuple_of_dicts_dump",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
