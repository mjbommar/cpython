from __future__ import annotations

import ast
import json
import os
import statistics
import time
from pathlib import Path


CASE_SOURCES: dict[str, str] = {
    "C1_module_assign": "x = 1\ny = x + 2\n",
    "C2_module_many_assign": "\n".join(f"v_{i} = {i}" for i in range(200)) + "\n",
    "C3_function_module": (
        "def f(x, y=2):\n"
        "    z = x + y\n"
        "    return z\n"
    ),
    "C4_class_module": (
        "class C:\n"
        "    scale = 3\n"
        "    def f(self, x):\n"
        "        return self.scale + x\n"
    ),
    "C5_nested_functions": (
        "def outer(x):\n"
        "    y = x + 1\n"
        "    def inner(z):\n"
        "        return y + z\n"
        "    return inner\n"
    ),
    "C6_list_comprehension": "result = [x * 2 for x in range(50) if x % 3]\n",
}


def benchmark_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONHASHSEED", "0")
    return env


def parse_cases() -> dict[str, ast.AST]:
    return {
        name: ast.parse(source, filename=f"<{name}>", mode="exec")
        for name, source in CASE_SOURCES.items()
    }


def run_case(
    tree: ast.AST,
    *,
    warmups: int,
    loops: int,
    inner_loops: int,
) -> dict[str, object]:
    for _ in range(warmups):
        for _ in range(inner_loops):
            compile(tree, "<bench>", "exec")

    samples = []
    for _ in range(loops):
        start = time.perf_counter_ns()
        for _ in range(inner_loops):
            compile(tree, "<bench>", "exec")
        samples.append(time.perf_counter_ns() - start)

    return {
        "warmups": warmups,
        "loops": loops,
        "inner_loops": inner_loops,
        "samples_ns": samples,
        "mean_ns": statistics.fmean(samples),
        "median_ns": statistics.median(samples),
        "min_ns": min(samples),
        "max_ns": max(samples),
    }


def save_results(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
