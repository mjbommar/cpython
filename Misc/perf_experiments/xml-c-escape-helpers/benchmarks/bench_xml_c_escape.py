#!/usr/bin/env python3
"""Focused benchmark for C-backed ElementTree XML escaping helpers."""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import statistics
import time
from xml.etree import ElementTree as ET


def _element(tag: str, text: str | None = None, attrib: dict[str, str] | None = None):
    elem = ET.Element(tag, attrib or {})
    elem.text = text
    return elem


def _build_tree(width: int, depth: int, *, escaped: bool) -> ET.Element:
    if escaped:
        root = _element("root", "clean & escaped <root> text", {"name": "a&b", "kind": '"quoted"'})
    else:
        root = _element("root", "clean text payload", {"name": "alpha", "kind": "plain"})
    level = [root]
    for d in range(depth):
        next_level = []
        for parent in level:
            for i in range(width):
                if escaped:
                    child = _element(
                        "cell",
                        f"value {d} & {i} <payload> >",
                        {"row": str(d), "col": str(i), "label": 'needs "quotes"\nline'},
                    )
                else:
                    child = _element(
                        "cell",
                        f"value {d} {i} clean payload",
                        {"row": str(d), "col": str(i), "label": "simple value"},
                    )
                parent.append(child)
                next_level.append(child)
        level = next_level
    return root


CLEAN_TEXT = "plain alpha beta gamma delta" * 2
LONG_CLEAN_TEXT = "plain alpha beta gamma delta " * 80
ESCAPE_TEXT = "alpha & beta < gamma > delta"
CLEAN_ATTRIB = "attribute plain alpha beta gamma"
LONG_CLEAN_ATTRIB = "attribute plain alpha beta gamma " * 80
ESCAPE_ATTRIB = 'alpha & beta < gamma > delta "quote"\nline\tindent\rreturn'
CLEAN_TREE = _build_tree(width=5, depth=3, escaped=False)
ESCAPE_TREE = _build_tree(width=5, depth=3, escaped=True)


def _serialize(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode", short_empty_elements=True)


def _measure(label: str, func, *, loops: int, repeat: int) -> dict[str, object]:
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


def _cases() -> dict[str, tuple[object, int]]:
    return {
        "E1_escape_cdata_clean_short": (lambda: ET._escape_cdata(CLEAN_TEXT), 200_000),
        "E2_escape_cdata_clean_long": (lambda: ET._escape_cdata(LONG_CLEAN_TEXT), 30_000),
        "E3_escape_cdata_dirty": (lambda: ET._escape_cdata(ESCAPE_TEXT), 120_000),
        "E4_escape_attrib_clean_short": (lambda: ET._escape_attrib(CLEAN_ATTRIB), 160_000),
        "E5_escape_attrib_clean_long": (lambda: ET._escape_attrib(LONG_CLEAN_ATTRIB), 20_000),
        "E6_escape_attrib_dirty": (lambda: ET._escape_attrib(ESCAPE_ATTRIB), 80_000),
        "E7_tostring_clean_tree": (lambda: _serialize(CLEAN_TREE), 2_500),
        "E8_tostring_escape_tree": (lambda: _serialize(ESCAPE_TREE), 2_000),
    }


def _profile(iterations: int) -> str:
    profile = cProfile.Profile()
    profile.enable()
    for _ in range(iterations):
        ET._escape_cdata(CLEAN_TEXT)
        ET._escape_attrib(CLEAN_ATTRIB)
        _serialize(CLEAN_TREE)
    profile.disable()
    out = io.StringIO()
    pstats.Stats(profile, stream=out).strip_dirs().sort_stats("tottime").print_stats(30)
    return out.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--loops-scale", type=float, default=1.0)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--profile-iterations", type=int, default=1_000)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    if ns.profile:
        print(_profile(ns.profile_iterations))
        return

    results = {}
    for name, (func, base_loops) in _cases().items():
        loops = max(1, int(base_loops * ns.loops_scale))
        results[name] = _measure(name, func, loops=loops, repeat=ns.repeat)

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    for name, result in results.items():
        print(f"{name}: best={result['best_ns']:.1f} ns mean={result['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
