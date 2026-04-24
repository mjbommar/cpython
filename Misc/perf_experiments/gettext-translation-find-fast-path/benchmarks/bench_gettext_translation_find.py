#!/usr/bin/env python3
"""Focused benchmark for gettext translation/find fast-path ideas."""

from __future__ import annotations

import argparse
import contextlib
import gettext
import json
import os
import pathlib
import statistics
import tempfile
import time


_TMPDIR = tempfile.TemporaryDirectory(prefix="perf-gettext-")
_LOCALEDIR = pathlib.Path(_TMPDIR.name, "locale")
_LOCALEDIR.mkdir()
_DEVNULL = open(os.devnull, "w")

_ORIGINAL_EXPAND_LANG = gettext._expand_lang
_CURRENT_DOMAIN = gettext.textdomain()


def _configure_env() -> None:
    os.environ["LANGUAGE"] = "fr_FR.UTF-8@euro:en_US.UTF-8"
    os.environ.pop("LC_ALL", None)
    os.environ.pop("LC_MESSAGES", None)
    os.environ["LANG"] = "C.UTF-8"
    gettext.bindtextdomain(_CURRENT_DOMAIN, str(_LOCALEDIR))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool",
        description="demo parser",
        epilog="bye",
    )
    parser.add_argument("--count", type=int, required=True, help="count value")
    parser.add_argument("--mode", choices=("a", "b", "c"), default="a", help="mode")
    parser.add_argument("name", nargs="?", help="name")
    return parser


def _argparse_ctor() -> argparse.ArgumentParser:
    return _build_parser()


def _argparse_help() -> str:
    return _build_parser().format_help()


def _argparse_error() -> str:
    parser = _build_parser()
    with contextlib.redirect_stderr(_DEVNULL):
        try:
            parser.parse_args(["--mode", "z"])
        except SystemExit:
            return "system-exit"
    raise AssertionError("expected parser error")


def _cached_expand_lang(loc):
    cached = _cached_expand_lang._cache.get(loc)
    if cached is not None:
        return cached.copy()
    result = _ORIGINAL_EXPAND_LANG(loc)
    _cached_expand_lang._cache[loc] = result
    return result.copy()


_cached_expand_lang._cache = {}


class Variant:
    def __init__(self, variant: str) -> None:
        self.variant = variant

    def __enter__(self):
        if self.variant == "cached_expand_lang":
            _cached_expand_lang._cache.clear()
            gettext._expand_lang = _cached_expand_lang
        return self

    def __exit__(self, exc_type, exc, tb):
        gettext._expand_lang = _ORIGINAL_EXPAND_LANG
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
    _configure_env()

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=("runtime", "cached_expand_lang"), default="runtime")
    parser.add_argument("--loops-direct", type=int, default=20_000)
    parser.add_argument("--loops-argparse", type=int, default=3_000)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "G1_expand_lang": measure(
                "expand_lang",
                lambda: gettext._expand_lang("fr_FR.UTF-8@euro"),
                loops=ns.loops_direct,
                repeat=ns.repeat,
            ),
            "G2_find_missing_explicit": measure(
                "find_missing_explicit",
                lambda: gettext.find(_CURRENT_DOMAIN, str(_LOCALEDIR), ["fr_FR.UTF-8@euro"], all=True),
                loops=ns.loops_direct,
                repeat=ns.repeat,
            ),
            "G3_find_missing_default_env": measure(
                "find_missing_default_env",
                lambda: gettext.find(_CURRENT_DOMAIN, str(_LOCALEDIR), None, all=True),
                loops=ns.loops_direct,
                repeat=ns.repeat,
            ),
            "G4_dgettext_missing": measure(
                "dgettext_missing",
                lambda: gettext.dgettext(_CURRENT_DOMAIN, "usage:"),
                loops=ns.loops_direct,
                repeat=ns.repeat,
            ),
            "G5_gettext_missing": measure(
                "gettext_missing",
                lambda: gettext.gettext("usage:"),
                loops=ns.loops_direct,
                repeat=ns.repeat,
            ),
            "G6_argparse_ctor": measure(
                "argparse_ctor",
                _argparse_ctor,
                loops=ns.loops_argparse,
                repeat=ns.repeat,
            ),
            "G7_argparse_help": measure(
                "argparse_help",
                _argparse_help,
                loops=ns.loops_argparse,
                repeat=ns.repeat,
            ),
            "G8_argparse_error": measure(
                "argparse_error",
                _argparse_error,
                loops=ns.loops_argparse,
                repeat=ns.repeat,
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "G1_expand_lang",
        "G2_find_missing_explicit",
        "G3_find_missing_default_env",
        "G4_dgettext_missing",
        "G5_gettext_missing",
        "G6_argparse_ctor",
        "G7_argparse_help",
        "G8_argparse_error",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
