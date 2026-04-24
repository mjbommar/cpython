#!/usr/bin/env python3
"""Focused benchmark for argparse _parse_known_args fast-path ideas."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


class Variant:
    def __init__(self, variant: str) -> None:
        self.variant = variant

    def __enter__(self):
        if self.variant == "no_mutex_fast_path":
            install_candidate()
        return self

    def __exit__(self, exc_type, exc, tb):
        restore_original()
        return False


def _build_simple_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--mode", choices=("a", "b", "c"), default="a")
    parser.add_argument("name")
    return parser


def _build_defaults_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--ratio", type=float, default=1.5)
    parser.add_argument("name", nargs="?")
    parser.set_defaults(extra="x")
    return parser


def _build_option_heavy_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    parser.add_argument("-a", action="store_true")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-c", action="store_true")
    parser.add_argument("--count", type=int, default=0)
    parser.add_argument("--name", default="anon")
    parser.add_argument("--mode", choices=("a", "b", "c"), default="a")
    parser.add_argument("src")
    parser.add_argument("dst")
    return parser


def _build_mutex_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--left", action="store_true")
    group.add_argument("--right", action="store_true")
    parser.add_argument("name")
    return parser


def _build_fromfile_parser() -> tuple[argparse.ArgumentParser, pathlib.Path]:
    parser = argparse.ArgumentParser(prog="tool", fromfile_prefix_chars="@")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("name")
    tmp = tempfile.NamedTemporaryFile("w", delete=False, prefix="perf-argparse-", suffix=".txt")
    tmp.write("--count\n7\nalice\n")
    tmp.close()
    return parser, pathlib.Path(tmp.name)


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
    cli = argparse.ArgumentParser()
    cli.add_argument("--variant", choices=("baseline", "no_mutex_fast_path"), default="baseline")
    cli.add_argument("--loops", type=int, default=4_000)
    cli.add_argument("--repeat", type=int, default=7)
    cli.add_argument("--json", action="store_true")
    ns = cli.parse_args()

    simple = _build_simple_parser()
    defaults = _build_defaults_parser()
    option_heavy = _build_option_heavy_parser()
    mutex = _build_mutex_parser()
    fromfile, fromfile_path = _build_fromfile_parser()

    try:
        with Variant(ns.variant):
            results = {
                "variant": ns.variant,
                "A1_simple_parse_known_args": measure(
                    "simple_parse_known_args",
                    lambda: simple.parse_known_args(["--count", "3", "alice"]),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "A2_simple_parse_args": measure(
                    "simple_parse_args",
                    lambda: simple.parse_args(["--count", "3", "alice"]),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "A3_defaults_namespace": measure(
                    "defaults_namespace",
                    lambda: defaults.parse_known_args(["bob"], argparse.Namespace(existing=1)),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "A4_option_heavy": measure(
                    "option_heavy",
                    lambda: option_heavy.parse_args(
                        ["-a", "-c", "--count", "9", "--name", "bob", "--mode", "b", "src", "dst"]
                    ),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "A5_intermixed": measure(
                    "intermixed",
                    lambda: option_heavy.parse_known_intermixed_args(
                        ["src", "-a", "--count", "9", "dst", "--mode", "b"]
                    ),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "A6_mutex_control": measure(
                    "mutex_control",
                    lambda: mutex.parse_args(["--left", "alice"]),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "A7_fromfile_control": measure(
                    "fromfile_control",
                    lambda: fromfile.parse_args([f"@{fromfile_path}"]),
                    loops=max(200, ns.loops // 8),
                    repeat=ns.repeat,
                ),
            }
    finally:
        fromfile_path.unlink(missing_ok=True)

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "A1_simple_parse_known_args",
        "A2_simple_parse_args",
        "A3_defaults_namespace",
        "A4_option_heavy",
        "A5_intermixed",
        "A6_mutex_control",
        "A7_fromfile_control",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
