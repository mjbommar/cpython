#!/usr/bin/env python3
"""Focused benchmark for _PyPegen_run_parser_from_string() entry costs."""

from __future__ import annotations

import argparse
import ast
import codeop
import json
import statistics
import symtable
import textwrap
import time


SOURCES = {
    "exec_small": "x = 1\ny = x + 41\n",
    "eval_small": "1 + 2 + 3 + 4",
    "function_module": textwrap.dedent(
        """
        def outer(a):
            factor = 3
            def inner(b):
                return a * factor + b
            return inner(5)

        result = outer(7)
        """
    ),
    "type_comments": textwrap.dedent(
        """
        value = []  # type: list[int]
        other = 3   # type: int
        """
    ),
    "incomplete": "if True:\n",
}


def _compile_exec_small():
    return compile(SOURCES["exec_small"], "<bench>", "exec")


def _compile_eval_small():
    return compile(SOURCES["eval_small"], "<bench>", "eval")


def _compile_function_module():
    return compile(SOURCES["function_module"], "<bench>", "exec")


def _ast_parse_function_module():
    return ast.parse(SOURCES["function_module"], filename="<bench>", mode="exec")


def _ast_parse_type_comments():
    return ast.parse(
        SOURCES["type_comments"],
        filename="<bench>",
        mode="exec",
        type_comments=True,
    )


def _symtable_function_module():
    return symtable.symtable(SOURCES["function_module"], "<bench>", "exec")


def _codeop_incomplete():
    return codeop.compile_command(SOURCES["incomplete"], filename="<bench>", symbol="exec")


BENCHES = {
    "P1_compile_exec_small": ("compile exec small", _compile_exec_small),
    "P2_compile_eval_small": ("compile eval small", _compile_eval_small),
    "P3_compile_function_module": ("compile function module", _compile_function_module),
    "P4_ast_parse_function_module": ("ast.parse function module", _ast_parse_function_module),
    "P5_ast_parse_type_comments": ("ast.parse type comments", _ast_parse_type_comments),
    "P6_symtable_function_module": ("symtable function module", _symtable_function_module),
    "P7_codeop_incomplete": ("codeop incomplete", _codeop_incomplete),
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
    parser.add_argument("--loops", type=int, default=20_000)
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

    for key in BENCHES:
        result = results[key]
        print(
            f"{result['label']}: best={result['best_ns']} ns "
            f"mean={result['mean_ns']} ns samples={result['samples_ns']}"
        )


if __name__ == "__main__":
    main()
