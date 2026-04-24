#!/usr/bin/env python3
"""Focused benchmark for marshal code-object load fast paths."""

from __future__ import annotations

import argparse
import importlib._bootstrap_external as _bootstrap_external
import json
import marshal
import statistics
import textwrap
import time


def _make_payload(filename: str, source: str) -> tuple[object, bytes]:
    code = compile(textwrap.dedent(source), filename, "exec")
    return code, marshal.dumps(code)


def _build_cases() -> dict[str, dict[str, object]]:
    cases = {}
    sources = {
        "tiny": """
            value = 1
            answer = value + 41
        """,
        "nested": """
            def outer(a):
                factor = 3
                def inner(b):
                    return a * factor + b
                return inner(5)

            result = outer(7)
        """,
        "many_consts": """
            TABLE = {
                "aa": 1, "ab": 2, "ac": 3, "ad": 4, "ae": 5, "af": 6, "ag": 7,
                "ba": 8, "bb": 9, "bc": 10, "bd": 11, "be": 12, "bf": 13, "bg": 14,
                "ca": 15, "cb": 16, "cc": 17, "cd": 18, "ce": 19, "cf": 20, "cg": 21,
            }

            def lookup(key):
                return TABLE.get(key, -1)

            result = lookup("cf")
        """,
        "class_methods": """
            class Greeter:
                prefix = "hello"

                def __init__(self, name):
                    self.name = name

                def render(self):
                    return f"{self.prefix}, {self.name}"

            greeting = Greeter("world").render()
        """,
    }
    for name, source in sources.items():
        code, payload = _make_payload(f"{name}.py", source)
        cases[name] = {
            "code": code,
            "payload": payload,
            "pyc_path": f"{name}.pyc",
            "source_path": f"{name}.py",
        }
    return cases


CASES = _build_cases()


def _marshal_load(case: str):
    return marshal.loads(CASES[case]["payload"])


def _compile_bytecode(case: str):
    return _bootstrap_external._compile_bytecode(
        CASES[case]["payload"],
        name=case,
        bytecode_path=CASES[case]["pyc_path"],
        source_path=CASES[case]["source_path"],
    )


BENCHES = {
    "M1_load_tiny": ("marshal.loads tiny", lambda: _marshal_load("tiny")),
    "M2_load_nested": ("marshal.loads nested", lambda: _marshal_load("nested")),
    "M3_load_many_consts": ("marshal.loads many consts", lambda: _marshal_load("many_consts")),
    "M4_load_class_methods": ("marshal.loads class methods", lambda: _marshal_load("class_methods")),
    "I1_compile_bytecode_tiny": ("_compile_bytecode tiny", lambda: _compile_bytecode("tiny")),
    "I2_compile_bytecode_nested": ("_compile_bytecode nested", lambda: _compile_bytecode("nested")),
    "I3_compile_bytecode_many_consts": (
        "_compile_bytecode many consts",
        lambda: _compile_bytecode("many_consts"),
    ),
    "I4_compile_bytecode_class_methods": (
        "_compile_bytecode class methods",
        lambda: _compile_bytecode("class_methods"),
    ),
}


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
    parser.add_argument("--loops", type=int, default=25_000)
    parser.add_argument("--repeat", type=int, default=9)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    results = {
        key: measure(label, func, loops=ns.loops, repeat=ns.repeat)
        for key, (label, func) in BENCHES.items()
    }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    for key in (
        "M1_load_tiny",
        "M2_load_nested",
        "M3_load_many_consts",
        "M4_load_class_methods",
        "I1_compile_bytecode_tiny",
        "I2_compile_bytecode_nested",
        "I3_compile_bytecode_many_consts",
        "I4_compile_bytecode_class_methods",
    ):
        result = results[key]
        print(
            f"{result['label']}: best={result['best_ns']} ns "
            f"mean={result['mean_ns']} ns samples={result['samples_ns']}"
        )


if __name__ == "__main__":
    main()
