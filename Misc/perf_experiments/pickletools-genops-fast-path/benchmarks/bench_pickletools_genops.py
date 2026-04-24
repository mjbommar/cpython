#!/usr/bin/env python3
"""Focused benchmark for pickletools._genops() fast-path ideas."""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import pickle
import pickletools
import statistics
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


class NoTellReader:
    def __init__(self, data: bytes) -> None:
        self._bio = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._bio.read(n)


SMALL_LIST = pickle.dumps(list(range(100)), protocol=5)
INT_TUPLE = pickle.dumps(tuple(range(256)), protocol=5)
NESTED_DICT = pickle.dumps(
    {"items": [{"id": i, "name": f"n{i}", "tags": [i, i + 1, i + 2]} for i in range(80)]},
    protocol=5,
)
FRAME_HEAVY = pickle.dumps((["x" * 64] * 400, {"k": list(range(100))}), protocol=5)
PROTO2_MIXED = pickle.dumps([("x", i, i % 7 == 0) for i in range(120)], protocol=2)


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


def _consume_genops(payload: bytes) -> int:
    count = 0
    for opcode, arg, pos in pickletools.genops(payload):
        count += 1
        if arg is not None:
            count += 1
        if pos is not None:
            count += 1
        if opcode.name == "STOP":
            count += 1
    return count


def _consume_genops_end(payload: bytes) -> int:
    count = 0
    for opcode, arg, pos, end_pos in pickletools._genops(payload, yield_end_pos=True):
        count += 1
        if arg is not None:
            count += 1
        if pos is not None:
            count += 1
        if end_pos is not None:
            count += 1
    return count


def _consume_genops_no_tell(payload: bytes) -> int:
    count = 0
    for opcode, arg, pos in pickletools._genops(NoTellReader(payload), yield_end_pos=False):
        count += 1
        if arg is not None:
            count += 1
        if pos is None:
            count += 1
    return count


def _optimize(payload: bytes) -> int:
    return len(pickletools.optimize(payload))


def _dis(payload: bytes) -> int:
    out = io.StringIO()
    pickletools.dis(payload, out=out)
    return len(out.getvalue())


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
    parser.add_argument("--variant", choices=("baseline", "byte_table"), default="baseline")
    parser.add_argument("--loops-small", type=int, default=4000)
    parser.add_argument("--loops-medium", type=int, default=1400)
    parser.add_argument("--loops-large", type=int, default=400)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "G1_genops_small_list": measure(
                "genops_small_list",
                lambda: _consume_genops(SMALL_LIST),
                loops=ns.loops_small,
                repeat=ns.repeat,
            ),
            "G2_genops_int_tuple": measure(
                "genops_int_tuple",
                lambda: _consume_genops(INT_TUPLE),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "G3_genops_nested_dict": measure(
                "genops_nested_dict",
                lambda: _consume_genops(NESTED_DICT),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "G4_genops_end_frame_heavy": measure(
                "genops_end_frame_heavy",
                lambda: _consume_genops_end(FRAME_HEAVY),
                loops=max(120, ns.loops_large // 2),
                repeat=ns.repeat,
            ),
            "G5_genops_no_tell_proto2": measure(
                "genops_no_tell_proto2",
                lambda: _consume_genops_no_tell(PROTO2_MIXED),
                loops=ns.loops_medium,
                repeat=ns.repeat,
            ),
            "G6_optimize_frame_heavy": measure(
                "optimize_frame_heavy",
                lambda: _optimize(FRAME_HEAVY),
                loops=max(80, ns.loops_large // 4),
                repeat=ns.repeat,
            ),
            "G7_dis_nested_dict": measure(
                "dis_nested_dict",
                lambda: _dis(NESTED_DICT),
                loops=max(80, ns.loops_large // 4),
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "G1_genops_small_list",
        "G2_genops_int_tuple",
        "G3_genops_nested_dict",
        "G4_genops_end_frame_heavy",
        "G5_genops_no_tell_proto2",
        "G6_optimize_frame_heavy",
        "G7_dis_nested_dict",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
