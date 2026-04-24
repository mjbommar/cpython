#!/usr/bin/env python3
"""Focused benchmark for pure-Python pickle load/read fast-path ideas."""

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


SMALL_LIST = list(range(100))
NESTED = [{"k": i, "v": [i, i + 1, i + 2], "s": f"value-{i}"} for i in range(80)]
STRINGS = [f"name-{i:04d}" for i in range(1000)]
LARGE_BYTES = bytearray(b"x" * (256 * 1024))
HUGE_BYTES = bytearray(b"y" * (3 * 1024 * 1024))
MULTI_OBJECTS = [list(range(i, i + 20)) for i in range(0, 1000, 10)]

PAYLOAD_SMALL_LIST = pickle._dumps(SMALL_LIST, protocol=5)
PAYLOAD_NESTED = pickle._dumps(NESTED, protocol=5)
PAYLOAD_STRINGS = pickle._dumps(STRINGS, protocol=5)
PAYLOAD_LARGE_BYTES = pickle._dumps(LARGE_BYTES, protocol=5)
PAYLOAD_HUGE_BYTES = pickle._dumps(HUGE_BYTES, protocol=5)
PAYLOAD_MULTI_STREAM = b"".join(pickle._dumps(obj, protocol=5) for obj in MULTI_OBJECTS)
CHUNK_DATA_2MB = b"a" * (2 * 1024 * 1024)
CHUNK_DATA_8MB = b"b" * (8 * 1024 * 1024)


def _load_stream_multi():
    unpickler = pickle._Unpickler(io.BytesIO(PAYLOAD_MULTI_STREAM))
    out = []
    for _ in range(len(MULTI_OBJECTS)):
        out.append(unpickler.load())
    return out


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


def _chunked_read_payload(data: bytes) -> bytes:
    bio = io.BytesIO(data)
    u = pickle._Unframer(bio.read, bio.readline)
    return u._chunked_file_read(len(data))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=(
            "baseline",
            "small_read_fast_path",
            "chunk_join",
            "chunk_bytearray",
            "chunk_join_large_only",
        ),
        default="baseline",
    )
    parser.add_argument("--loops", type=int, default=1200)
    parser.add_argument("--loops-large", type=int, default=250)
    parser.add_argument("--loops-huge", type=int, default=60)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "P1_load_small_list": measure(
                "load_small_list",
                lambda: pickle._loads(PAYLOAD_SMALL_LIST),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "P2_load_nested": measure(
                "load_nested",
                lambda: pickle._loads(PAYLOAD_NESTED),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "P3_load_strings": measure(
                "load_strings",
                lambda: pickle._loads(PAYLOAD_STRINGS),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "P4_load_stream_multi": measure(
                "load_stream_multi",
                _load_stream_multi,
                loops=max(200, ns.loops // 4),
                repeat=ns.repeat,
            ),
            "P5_load_large_bytes": measure(
                "load_large_bytes",
                lambda: pickle._loads(PAYLOAD_LARGE_BYTES),
                loops=ns.loops_large,
                repeat=ns.repeat,
            ),
            "P6_load_huge_bytes": measure(
                "load_huge_bytes",
                lambda: pickle._loads(PAYLOAD_HUGE_BYTES),
                loops=ns.loops_huge,
                repeat=ns.repeat,
            ),
            "P7_chunked_read_2mb": measure(
                "chunked_read_2mb",
                lambda: _chunked_read_payload(CHUNK_DATA_2MB),
                loops=ns.loops_huge,
                repeat=ns.repeat,
            ),
            "P8_chunked_read_8mb": measure(
                "chunked_read_8mb",
                lambda: _chunked_read_payload(CHUNK_DATA_8MB),
                loops=max(20, ns.loops_huge // 3),
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "P1_load_small_list",
        "P2_load_nested",
        "P3_load_strings",
        "P4_load_stream_multi",
        "P5_load_large_bytes",
        "P6_load_huge_bytes",
        "P7_chunked_read_2mb",
        "P8_chunked_read_8mb",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
