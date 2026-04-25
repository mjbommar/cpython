#!/usr/bin/env python3
"""Focused benchmark for tokenize.detect_encoding fast-path ideas."""

from __future__ import annotations

import argparse
import importlib._bootstrap_external as bootstrap_external
import io
import json
import pathlib
import statistics
import sys
import tempfile
import time
import tokenize


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


DEFAULT_ASCII = b'"""module doc"""\nimport os\n'
DEFAULT_UTF8 = '"""caf\xe9"""\nimport sys\n'.encode("utf-8")
COMMENT_COOKIE = b"# coding: latin-1\nx = 1\n"
SHEBANG_COOKIE = b"#!/usr/bin/env python3\n# coding: latin-1\nx = 1\n"
BOM_DEFAULT = tokenize.BOM_UTF8 + b'"""bom"""\npass\n'
COOKIE_LATIN1 = b"# coding: latin-1\ns = 'caf\xe9'\n"


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "common_case_split"),
        default="baseline",
    )
    parser.add_argument("--loops-detect", type=int, default=12000)
    parser.add_argument("--loops-file", type=int, default=2500)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="perf-tokenize-detect-") as tmp:
        tmpdir = pathlib.Path(tmp)
        default_path = tmpdir / "default.py"
        cookie_path = tmpdir / "cookie.py"
        default_path.write_bytes(DEFAULT_UTF8)
        cookie_path.write_bytes(COOKIE_LATIN1)

        with Variant(ns.variant):
            results = {
                "variant": ns.variant,
                "T1_detect_ascii_docstring": measure(
                    "detect_ascii_docstring",
                    lambda: tokenize.detect_encoding(io.BytesIO(DEFAULT_ASCII).readline),
                    loops=ns.loops_detect,
                    repeat=ns.repeat,
                ),
                "T2_detect_utf8_docstring": measure(
                    "detect_utf8_docstring",
                    lambda: tokenize.detect_encoding(io.BytesIO(DEFAULT_UTF8).readline),
                    loops=ns.loops_detect,
                    repeat=ns.repeat,
                ),
                "T3_detect_comment_cookie": measure(
                    "detect_comment_cookie",
                    lambda: tokenize.detect_encoding(io.BytesIO(COMMENT_COOKIE).readline),
                    loops=ns.loops_detect,
                    repeat=ns.repeat,
                ),
                "T4_detect_shebang_cookie": measure(
                    "detect_shebang_cookie",
                    lambda: tokenize.detect_encoding(io.BytesIO(SHEBANG_COOKIE).readline),
                    loops=ns.loops_detect,
                    repeat=ns.repeat,
                ),
                "T5_detect_bom_default": measure(
                    "detect_bom_default",
                    lambda: tokenize.detect_encoding(io.BytesIO(BOM_DEFAULT).readline),
                    loops=ns.loops_detect,
                    repeat=ns.repeat,
                ),
                "T6_open_default": measure(
                    "open_default",
                    lambda: tokenize.open(default_path).close(),
                    loops=ns.loops_file,
                    repeat=ns.repeat,
                ),
                "T7_open_cookie": measure(
                    "open_cookie",
                    lambda: tokenize.open(cookie_path).close(),
                    loops=ns.loops_file,
                    repeat=ns.repeat,
                ),
                "T8_decode_source_default": measure(
                    "decode_source_default",
                    lambda: bootstrap_external.decode_source(DEFAULT_UTF8),
                    loops=ns.loops_detect,
                    repeat=ns.repeat,
                ),
            }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "T1_detect_ascii_docstring",
        "T2_detect_utf8_docstring",
        "T3_detect_comment_cookie",
        "T4_detect_shebang_cookie",
        "T5_detect_bom_default",
        "T6_open_default",
        "T7_open_cookie",
        "T8_decode_source_default",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
