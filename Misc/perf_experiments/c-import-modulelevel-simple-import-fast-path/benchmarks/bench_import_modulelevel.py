#!/usr/bin/env python3
"""Focused benchmark for C import-module-level fast paths."""

from __future__ import annotations

import argparse
import json
import statistics
import time


def _plain_math():
    import math
    return math


def _plain_json():
    import json
    return json


def _dotted_email():
    import email.parser
    return email


def _dotted_xml():
    import xml.etree.ElementTree
    return xml


def _from_email():
    from email import parser
    return parser


def _from_xml():
    from xml.etree import ElementTree
    return ElementTree


def _builtin_import_default():
    return __import__("math")


def _builtin_import_empty_tuple():
    return __import__("math", globals(), locals(), (), 0)


BENCHES = {
    "I1_plain_math": ("import math", _plain_math),
    "I2_plain_json": ("import json", _plain_json),
    "I3_dotted_email": ("import email.parser", _dotted_email),
    "I4_dotted_xml": ("import xml.etree.ElementTree", _dotted_xml),
    "I5_from_email": ("from email import parser", _from_email),
    "I6_from_xml": ("from xml.etree import ElementTree", _from_xml),
    "I7_builtin_default": ("__import__('math')", _builtin_import_default),
    "I8_builtin_empty_tuple": (
        "__import__('math', globals(), locals(), (), 0)",
        _builtin_import_empty_tuple,
    ),
}


def _warm() -> None:
    for _, func in BENCHES.values():
        func()


def measure(label: str, func, *, loops: int, repeat: int) -> dict[str, object]:
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
    parser.add_argument("--loops", type=int, default=400_000)
    parser.add_argument("--repeat", type=int, default=9)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    _warm()
    results = {
        key: measure(label, func, loops=ns.loops, repeat=ns.repeat)
        for key, (label, func) in BENCHES.items()
    }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    for key in BENCHES:
        result = results[key]
        print(
            f"{result['label']}: best={result['best_ns']} ns "
            f"mean={result['mean_ns']} ns samples={result['samples_ns']}"
        )


if __name__ == "__main__":
    main()
