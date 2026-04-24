#!/usr/bin/env python3
"""Focused benchmark for pickle save-side atomic batch follow-up ideas."""

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

LIST_OF_INTS_10K = list(range(10_000))
LIST_OF_STRS_1K = [f"item_{i}" for i in range(1_000)]
LIST_OF_BYTES_1K = [f"item_{i}".encode() for i in range(1_000)]
NESTED_LIST_OF_DICTS = [{"id": i, "name": f"n{i}", "val": i * 2} for i in range(500)]
DEEP_LIST = [[i] * 10 for i in range(500)]
MIXED_SCALAR_LIST = [0, "x", 1.5, None, True] * 400
BOOL_LIST = [True, False] * 2_000
SMALL_INT_RUN = [7] * 128


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
        choices=(
            "baseline",
            "exact_bool_lists",
            "exact_str_lists",
            "exact_bytes_lists",
            "exact_atomic_lists",
        ),
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
            "S1_list_of_ints_10k_dump": measure(
                "list_of_ints_10k_dump",
                lambda: _dump(LIST_OF_INTS_10K),
                loops=ns.loops_large,
                repeat=ns.repeat,
            ),
            "S2_list_of_strs_1k_dump": measure(
                "list_of_strs_1k_dump",
                lambda: _dump(LIST_OF_STRS_1K),
                loops=max(200, ns.loops_medium // 2),
                repeat=ns.repeat,
            ),
            "S3_list_of_bytes_1k_dump": measure(
                "list_of_bytes_1k_dump",
                lambda: _dump(LIST_OF_BYTES_1K),
                loops=max(200, ns.loops_medium // 2),
                repeat=ns.repeat,
            ),
            "S4_nested_list_of_dicts_dump": measure(
                "nested_list_of_dicts_dump",
                lambda: _dump(NESTED_LIST_OF_DICTS),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "S5_deep_list_dump": measure(
                "deep_list_dump",
                lambda: _dump(DEEP_LIST),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "S6_mixed_scalar_list_dump": measure(
                "mixed_scalar_list_dump",
                lambda: _dump(MIXED_SCALAR_LIST),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "S7_bool_list_dump": measure(
                "bool_list_dump",
                lambda: _dump(BOOL_LIST),
                loops=ns.loops_small,
                repeat=ns.repeat,
            ),
            "S8_small_int_run_dump": measure(
                "small_int_run_dump",
                lambda: _dump(SMALL_INT_RUN),
                loops=ns.loops_small,
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "S1_list_of_ints_10k_dump",
        "S2_list_of_strs_1k_dump",
        "S3_list_of_bytes_1k_dump",
        "S4_nested_list_of_dicts_dump",
        "S5_deep_list_dump",
        "S6_mixed_scalar_list_dump",
        "S7_bool_list_dump",
        "S8_small_int_run_dump",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
