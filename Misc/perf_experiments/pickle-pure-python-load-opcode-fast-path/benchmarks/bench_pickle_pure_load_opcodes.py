#!/usr/bin/env python3
"""Focused benchmark for pure-Python pickle load opcode fast-path ideas."""

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


UNICODE_LIST = [f"name-{i:04d}" for i in range(1200)]
SMALL_INT_LIST = list(range(1200))
TUPLE3_LIST = [(i, i + 1, i + 2) for i in range(500)]
NESTED_MIXED = [
    {"name": f"n{i}", "vals": [i, i + 1, i + 2], "triple": (i, i + 1, i + 2)}
    for i in range(220)
]
MULTI_OBJECTS = [
    [f"s-{i}-{j}" for j in range(25)] for i in range(40)
] + [
    (i, i + 1, i + 2) for i in range(200)
] + [
    {"k": i, "ok": True, "n": i + 3} for i in range(120)
]

PAYLOAD_UNICODE = pickle._dumps(UNICODE_LIST, protocol=5)
PAYLOAD_SMALL_INTS = pickle._dumps(SMALL_INT_LIST, protocol=5)
PAYLOAD_TUPLE3 = pickle._dumps(TUPLE3_LIST, protocol=5)
PAYLOAD_NESTED = pickle._dumps(NESTED_MIXED, protocol=5)
PAYLOAD_MULTI_STREAM = b"".join(pickle._dumps(obj, protocol=5) for obj in MULTI_OBJECTS)


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


def load_stream_multi():
    unpickler = pickle._Unpickler(io.BytesIO(PAYLOAD_MULTI_STREAM))
    out = []
    for _ in range(len(MULTI_OBJECTS)):
        out.append(unpickler.load())
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "inline_hot_opcodes"),
        default="baseline",
    )
    parser.add_argument("--loops", type=int, default=700)
    parser.add_argument("--loops-stream", type=int, default=120)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "P1_load_unicode_list": measure(
                "load_unicode_list",
                lambda: pickle._loads(PAYLOAD_UNICODE),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "P2_load_small_int_list": measure(
                "load_small_int_list",
                lambda: pickle._loads(PAYLOAD_SMALL_INTS),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "P3_load_tuple3_list": measure(
                "load_tuple3_list",
                lambda: pickle._loads(PAYLOAD_TUPLE3),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "P4_load_nested_mixed": measure(
                "load_nested_mixed",
                lambda: pickle._loads(PAYLOAD_NESTED),
                loops=max(200, ns.loops // 2),
                repeat=ns.repeat,
            ),
            "P5_load_stream_multi": measure(
                "load_stream_multi",
                load_stream_multi,
                loops=ns.loops_stream,
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "P1_load_unicode_list",
        "P2_load_small_int_list",
        "P3_load_tuple3_list",
        "P4_load_nested_mixed",
        "P5_load_stream_multi",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
