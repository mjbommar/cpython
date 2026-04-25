"""Focused benchmark for 1-byte str.islower()/str.isupper() regimes."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import time


REPEATS = 7
TARGET_SECONDS = 0.08


def _latin1_lower_chars() -> str:
    chars = "".join(chr(c) for c in range(256) if not chr(c).isupper())
    assert chars.islower()
    return chars


def _latin1_upper_chars() -> str:
    chars = "".join(chr(c) for c in range(256) if not chr(c).islower())
    assert chars.isupper()
    return chars


ASCII_LOWER = "abcdefghijklmnopqrstuvwxyz" * 4096
ASCII_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4096
ASCII_UNCASED = "0123456789-_=+[]{};:,.<>/?! " * 4096
LATIN1_LOWER = _latin1_lower_chars() * 512
LATIN1_UPPER = _latin1_upper_chars() * 512
BMP_LOWER = "αβγδεζηθικλμνξοπρστυφχψω" * 4096
BMP_UPPER = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ" * 4096
NAMES = [
    "AF_INET",
    "SOCK_STREAM",
    "MSG_DONTWAIT",
    "AI_PASSIVE",
    "PyUnicode_KIND",
    "lowercase",
    "mixedCase",
] * 2048


CASES = {
    "islower_ascii_true": lambda: ASCII_LOWER.islower(),
    "islower_ascii_false_tail": lambda: (ASCII_LOWER + "A").islower(),
    "islower_ascii_uncased": lambda: ASCII_UNCASED.islower(),
    "islower_latin1_true": lambda: LATIN1_LOWER.islower(),
    "islower_latin1_false_tail": lambda: (LATIN1_LOWER + "A").islower(),
    "islower_bmp_true": lambda: BMP_LOWER.islower(),
    "isupper_ascii_true": lambda: ASCII_UPPER.isupper(),
    "isupper_ascii_false_tail": lambda: (ASCII_UPPER + "a").isupper(),
    "isupper_ascii_uncased": lambda: ASCII_UNCASED.isupper(),
    "isupper_latin1_true": lambda: LATIN1_UPPER.isupper(),
    "isupper_latin1_false_tail": lambda: (LATIN1_UPPER + "a").isupper(),
    "isupper_bmp_true": lambda: BMP_UPPER.isupper(),
    "stdlib_name_filters": lambda: (
        sum(name.isupper() for name in NAMES),
        sum(name.islower() for name in NAMES),
    ),
}


def calibrate(func):
    loops = 1
    while True:
        t0 = time.perf_counter()
        for _ in range(loops):
            func()
        elapsed = time.perf_counter() - t0
        if elapsed >= TARGET_SECONDS:
            return loops
        loops *= 2


def measure(func, loops):
    samples = []
    for _ in range(REPEATS):
        gc.collect()
        gc.disable()
        try:
            t0 = time.perf_counter()
            for _ in range(loops):
                func()
            elapsed = time.perf_counter() - t0
        finally:
            gc.enable()
        samples.append(elapsed / loops)
    return {
        "loops": loops,
        "best_ns": min(samples) * 1e9,
        "median_ns": statistics.median(samples) * 1e9,
        "samples_ns": [sample * 1e9 for sample in samples],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    args = parser.parse_args()

    results = {}
    for name, func in CASES.items():
        loops = calibrate(func)
        results[name] = measure(func, loops)

    text = json.dumps(results, indent=2, sort_keys=True)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(text)
            f.write("\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
