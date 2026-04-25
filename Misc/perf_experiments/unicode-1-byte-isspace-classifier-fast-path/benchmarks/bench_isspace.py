"""Focused benchmark for 1-byte str.isspace() regimes."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import textwrap
import time


REPEATS = 7
TARGET_SECONDS = 0.08


ASCII_SPACE = " \t\r\n\f\v" * 16384
LATIN1_SPACE = (" \t\r\n\f\v" + "\x1c\x1d\x1e\x1f\x85\xa0") * 8192
ASCII_WORD = "alpha beta gamma delta " * 8192
BMP_SPACE = "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a" * 8192
MIXED_LINES = [
    "    ",
    "\t\t",
    "alpha beta gamma",
    "",
    "\xa0\xa0",
    "delta",
] * 4096
TEXT = ("    alpha beta gamma\n\n        delta epsilon\n    \n") * 4096


CASES = {
    "isspace_ascii_true": lambda: ASCII_SPACE.isspace(),
    "isspace_ascii_false_tail": lambda: (ASCII_SPACE + "x").isspace(),
    "isspace_ascii_false_head": lambda: ("x" + ASCII_SPACE).isspace(),
    "isspace_latin1_true": lambda: LATIN1_SPACE.isspace(),
    "isspace_latin1_false_tail": lambda: (LATIN1_SPACE + "x").isspace(),
    "isspace_bmp_true": lambda: BMP_SPACE.isspace(),
    "line_filter": lambda: sum(line.isspace() for line in MIXED_LINES),
    "textwrap_dedent": lambda: textwrap.dedent(TEXT),
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
