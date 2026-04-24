from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path


CASE_SOURCES: dict[str, str] = {
    "S1_module_assign": "x = 1\ny = x + 2\n",
    "S2_nested_functions": (
        "def outer(x):\n"
        "    y = x + 1\n"
        "    def inner(z):\n"
        "        return y + z\n"
        "    return inner\n"
    ),
    "S3_class_methods": (
        "class C:\n"
        "    value = 3\n"
        "    def f(self, x):\n"
        "        return self.value + x\n"
        "    def g(self):\n"
        "        return self.f(4)\n"
    ),
    "S4_comprehensions": (
        "def f(xs):\n"
        "    return [x * 2 for x in xs if x % 3]\n"
    ),
    "S5_generic_function": (
        "def f[T](x: T, y: T) -> T:\n"
        "    return x if x else y\n"
    ),
    "S6_generic_class": (
        "class Box[T]:\n"
        "    def __init__(self, value: T):\n"
        "        self.value = value\n"
        "    def get(self) -> T:\n"
        "        return self.value\n"
    ),
}


def benchmark_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONHASHSEED", "0")
    return env


def measure_call(func, *, warmups: int, loops: int, inner_loops: int) -> dict[str, object]:
    for _ in range(warmups):
        for _ in range(inner_loops):
            func()

    samples = []
    for _ in range(loops):
        start = time.perf_counter_ns()
        for _ in range(inner_loops):
            func()
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
