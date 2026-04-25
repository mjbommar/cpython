#!/usr/bin/env python3
"""Focused benchmark for DecompressReader.read() fast-path ideas."""

from __future__ import annotations

import argparse
import bz2
import io
import json
import lzma
import pathlib
import statistics
import time

from compression._common import _streams
from _bz2 import BZ2Decompressor
from _lzma import LZMADecompressor, LZMAError


ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


PAYLOAD = (bytes(range(256)) * 512) + (b"header: value\n" * 4096)
PAYLOAD_A = PAYLOAD[: len(PAYLOAD) // 2]
PAYLOAD_B = PAYLOAD[len(PAYLOAD) // 2 :]
BZ2_DATA = bz2.compress(PAYLOAD, compresslevel=9)
LZMA_DATA = lzma.compress(PAYLOAD)
BZ2_MULTI = bz2.compress(PAYLOAD_A, compresslevel=9) + bz2.compress(PAYLOAD_B, compresslevel=9)
LZMA_MULTI = lzma.compress(PAYLOAD_A) + lzma.compress(PAYLOAD_B)


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


def run_raw(data: bytes, *, factory, trailing_error, chunk_size: int) -> bytes:
    reader = _streams.DecompressReader(io.BytesIO(data), factory, trailing_error=trailing_error)
    parts = []
    while True:
        chunk = reader.read(chunk_size)
        if not chunk:
            break
        parts.append(chunk)
    return b"".join(parts)


def run_file(file_factory, data: bytes, *, chunk_size: int) -> bytes:
    with file_factory(io.BytesIO(data), "rb") as fp:
        parts = []
        while True:
            chunk = fp.read(chunk_size)
            if not chunk:
                break
            parts.append(chunk)
    return b"".join(parts)


def run_readall(file_factory, data: bytes) -> bytes:
    with file_factory(io.BytesIO(data), "rb") as fp:
        return fp.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("baseline", "common_case_split"), default="baseline")
    parser.add_argument("--loops-raw", type=int, default=250)
    parser.add_argument("--loops-file", type=int, default=180)
    parser.add_argument("--loops-readall", type=int, default=120)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "C1_bz2_raw_chunked": measure(
                "bz2_raw_chunked",
                lambda: run_raw(BZ2_DATA, factory=BZ2Decompressor, trailing_error=OSError, chunk_size=8192),
                loops=ns.loops_raw,
                repeat=ns.repeat,
            ),
            "C2_lzma_raw_chunked": measure(
                "lzma_raw_chunked",
                lambda: run_raw(LZMA_DATA, factory=LZMADecompressor, trailing_error=LZMAError, chunk_size=8192),
                loops=ns.loops_raw,
                repeat=ns.repeat,
            ),
            "C3_bz2_raw_multistream": measure(
                "bz2_raw_multistream",
                lambda: run_raw(BZ2_MULTI, factory=BZ2Decompressor, trailing_error=OSError, chunk_size=4096),
                loops=ns.loops_raw,
                repeat=ns.repeat,
            ),
            "C4_lzma_raw_multistream": measure(
                "lzma_raw_multistream",
                lambda: run_raw(LZMA_MULTI, factory=LZMADecompressor, trailing_error=LZMAError, chunk_size=4096),
                loops=ns.loops_raw,
                repeat=ns.repeat,
            ),
            "C5_bz2_file_chunked": measure(
                "bz2_file_chunked",
                lambda: run_file(bz2.BZ2File, BZ2_DATA, chunk_size=8192),
                loops=ns.loops_file,
                repeat=ns.repeat,
            ),
            "C6_lzma_file_chunked": measure(
                "lzma_file_chunked",
                lambda: run_file(lzma.LZMAFile, LZMA_DATA, chunk_size=8192),
                loops=ns.loops_file,
                repeat=ns.repeat,
            ),
            "C7_bz2_file_readall": measure(
                "bz2_file_readall",
                lambda: run_readall(bz2.BZ2File, BZ2_DATA),
                loops=ns.loops_readall,
                repeat=ns.repeat,
            ),
            "C8_lzma_file_readall": measure(
                "lzma_file_readall",
                lambda: run_readall(lzma.LZMAFile, LZMA_DATA),
                loops=ns.loops_readall,
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "C1_bz2_raw_chunked",
        "C2_lzma_raw_chunked",
        "C3_bz2_raw_multistream",
        "C4_lzma_raw_multistream",
        "C5_bz2_file_chunked",
        "C6_lzma_file_chunked",
        "C7_bz2_file_readall",
        "C8_lzma_file_readall",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
