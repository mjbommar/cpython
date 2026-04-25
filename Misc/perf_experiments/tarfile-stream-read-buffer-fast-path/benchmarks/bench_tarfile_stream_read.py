#!/usr/bin/env python3
"""Focused benchmark for tarfile stream read ideas."""

from __future__ import annotations

import argparse
import io
import json
import pathlib
import statistics
import sys
import tarfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


PAYLOADS = {
    "alpha.txt": (b"alpha\n" * 400),
    "beta.bin": bytes(range(256)) * 96,
    "nested/gamma.txt": (b"gamma-data-" * 1800),
}


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


def build_archive(comptype: str) -> bytes:
    buf = io.BytesIO()
    mode = f"w|{comptype}"
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for name, data in PAYLOADS.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


ARCHIVES = {comptype: build_archive(comptype) for comptype in ("gz", "bz2", "xz")}


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


def read_stream_members(comptype: str, chunk_size: int) -> int:
    total = 0
    with tarfile.open(fileobj=io.BytesIO(ARCHIVES[comptype]), mode=f"r|{comptype}") as tf:
        for member in tf:
            total += len(member.name)
            if not member.isreg():
                continue
            with tf.extractfile(member) as f:
                while True:
                    block = f.read(chunk_size)
                    if not block:
                        break
                    total += len(block)
    return total


def iterate_stream_headers(comptype: str) -> int:
    total = 0
    with tarfile.open(fileobj=io.BytesIO(ARCHIVES[comptype]), mode=f"r|{comptype}") as tf:
        for member in tf:
            total += member.size
    return total


def direct_stream_read(comptype: str, size: int) -> int:
    stream = tarfile._Stream(
        "bench.tar",
        "r",
        comptype,
        io.BytesIO(ARCHIVES[comptype]),
        tarfile.RECORDSIZE,
        None,
        None,
    )
    try:
        total = 0
        while True:
            block = stream._read(size)
            if not block:
                break
            total += len(block)
        return total
    finally:
        stream.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "common_case_split", "common_case_split_direct"),
        default="baseline",
    )
    parser.add_argument("--loops", type=int, default=180)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "T1_gz_stream_member_small_reads": measure(
                "gz_stream_member_small_reads",
                lambda: read_stream_members("gz", 257),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "T2_bz2_stream_member_small_reads": measure(
                "bz2_stream_member_small_reads",
                lambda: read_stream_members("bz2", 257),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "T3_xz_stream_member_small_reads": measure(
                "xz_stream_member_small_reads",
                lambda: read_stream_members("xz", 257),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "T4_gz_stream_member_large_reads": measure(
                "gz_stream_member_large_reads",
                lambda: read_stream_members("gz", 4096),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "T5_bz2_stream_member_large_reads": measure(
                "bz2_stream_member_large_reads",
                lambda: read_stream_members("bz2", 4096),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "T6_xz_stream_member_large_reads": measure(
                "xz_stream_member_large_reads",
                lambda: read_stream_members("xz", 4096),
                loops=ns.loops,
                repeat=ns.repeat,
            ),
            "T7_gz_stream_headers_only": measure(
                "gz_stream_headers_only",
                lambda: iterate_stream_headers("gz"),
                loops=ns.loops * 2,
                repeat=ns.repeat,
            ),
            "T8_bz2_direct_small_reads": measure(
                "bz2_direct_small_reads",
                lambda: direct_stream_read("bz2", 257),
                loops=ns.loops * 2,
                repeat=ns.repeat,
            ),
            "T9_xz_direct_small_reads": measure(
                "xz_direct_small_reads",
                lambda: direct_stream_read("xz", 257),
                loops=ns.loops * 2,
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "T1_gz_stream_member_small_reads",
        "T2_bz2_stream_member_small_reads",
        "T3_xz_stream_member_small_reads",
        "T4_gz_stream_member_large_reads",
        "T5_bz2_stream_member_large_reads",
        "T6_xz_stream_member_large_reads",
        "T7_gz_stream_headers_only",
        "T8_bz2_direct_small_reads",
        "T9_xz_direct_small_reads",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
