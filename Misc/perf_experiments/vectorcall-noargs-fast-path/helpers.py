from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path


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
