#!/usr/bin/env python3
"""Guardrails for argparse _parse_known_args fast-path candidates."""

from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


def build_simple_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--mode", choices=("a", "b", "c"), default="a")
    parser.add_argument("name")
    return parser


def build_mutex_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--left", action="store_true")
    group.add_argument("--right", action="store_true")
    parser.add_argument("name")
    return parser


def build_fromfile_parser() -> tuple[argparse.ArgumentParser, pathlib.Path]:
    parser = argparse.ArgumentParser(prog="tool", fromfile_prefix_chars="@")
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("name")
    tmp = tempfile.NamedTemporaryFile("w", delete=False, prefix="guard-argparse-", suffix=".txt")
    tmp.write("--count\n7\nalice\n")
    tmp.close()
    return parser, pathlib.Path(tmp.name)


def capture(fn):
    try:
        result = fn()
    except BaseException as exc:  # noqa: BLE001
        return (type(exc), exc.args)
    return ("ok", result)


def main() -> None:
    simple = build_simple_parser()
    mutex = build_mutex_parser()
    fromfile, fromfile_path = build_fromfile_parser()
    try:
        baseline = {
            "simple_args": capture(lambda: simple.parse_args(["--count", "3", "alice"])),
            "simple_known": capture(lambda: simple.parse_known_args(["--count", "3", "alice", "extra"])),
            "simple_intermixed": capture(
                lambda: simple.parse_known_intermixed_args(["alice", "--count", "3", "extra"])
            ),
            "simple_ns": capture(
                lambda: simple.parse_known_args(["--count", "5", "bob"], argparse.Namespace(existing=1))
            ),
            "mutex_ok": capture(lambda: mutex.parse_args(["--left", "alice"])),
            "mutex_missing": capture(lambda: mutex.parse_args(["alice"])),
            "fromfile": capture(lambda: fromfile.parse_args([f"@{fromfile_path}"])),
        }

        install_candidate()
        simple2 = build_simple_parser()
        mutex2 = build_mutex_parser()
        fromfile2, fromfile_path2 = build_fromfile_parser()
        try:
            candidate = {
                "simple_args": capture(lambda: simple2.parse_args(["--count", "3", "alice"])),
                "simple_known": capture(
                    lambda: simple2.parse_known_args(["--count", "3", "alice", "extra"])
                ),
                "simple_intermixed": capture(
                    lambda: simple2.parse_known_intermixed_args(["alice", "--count", "3", "extra"])
                ),
                "simple_ns": capture(
                    lambda: simple2.parse_known_args(
                        ["--count", "5", "bob"], argparse.Namespace(existing=1)
                    )
                ),
                "mutex_ok": capture(lambda: mutex2.parse_args(["--left", "alice"])),
                "mutex_missing": capture(lambda: mutex2.parse_args(["alice"])),
                "fromfile": capture(lambda: fromfile2.parse_args([f"@{fromfile_path2}"])),
            }
        finally:
            fromfile_path2.unlink(missing_ok=True)
            restore_original()
    finally:
        fromfile_path.unlink(missing_ok=True)

    assert baseline == candidate, (baseline, candidate)
    print("argparse parse-known-args guardrails: ok")


if __name__ == "__main__":
    main()
