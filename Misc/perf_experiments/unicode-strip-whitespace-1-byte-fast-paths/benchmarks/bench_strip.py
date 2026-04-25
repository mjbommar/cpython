"""Focused benchmark for whitespace strip/lstrip/rstrip fast paths."""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import textwrap
import time


REPEATS = 7
TARGET_SECONDS = 0.08


SPACE_PADDED = " " * 128 + "alpha beta gamma delta" * 64 + " " * 128
TAB_SPACE_PADDED = "\t \t " * 32 + "alpha beta gamma delta" * 64 + " \t \t" * 32
NO_PAD = "alpha beta gamma delta" * 128
RIGHT_SPACE_PADDED = "alpha beta gamma delta" * 64 + " " * 256
LEFT_SPACE_PADDED = " " * 256 + "alpha beta gamma delta" * 64
LATIN1_PADDED = "\xa0" * 128 + "alpha beta gamma delta" * 64 + "\xa0" * 128
BMP_PADDED = "\u2000" * 128 + "alpha beta gamma delta" * 64 + "\u2000" * 128
EMAIL_LINES = [
    "    Subject: alpha beta gamma    ",
    "\t folded header value\t",
    "body line without padding",
    "        continuation    ",
] * 4096
DEDENT_TEXT = ("    alpha beta gamma\n\n        delta epsilon\n    \n") * 4096


CASES = {
    "strip_space_padded": lambda: SPACE_PADDED.strip(),
    "lstrip_space_padded": lambda: LEFT_SPACE_PADDED.lstrip(),
    "rstrip_space_padded": lambda: RIGHT_SPACE_PADDED.rstrip(),
    "strip_tab_space_padded": lambda: TAB_SPACE_PADDED.strip(),
    "strip_no_pad": lambda: NO_PAD.strip(),
    "strip_latin1_padded": lambda: LATIN1_PADDED.strip(),
    "strip_bmp_padded": lambda: BMP_PADDED.strip(),
    "email_line_trim": lambda: [line.strip() for line in EMAIL_LINES],
    "textwrap_dedent": lambda: textwrap.dedent(DEDENT_TEXT),
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
