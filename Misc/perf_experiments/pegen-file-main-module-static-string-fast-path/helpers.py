from __future__ import annotations

import json
import os
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


FAMILY_ROOT = Path(__file__).resolve().parent


def benchmark_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONHASHSEED", "0")
    return env


def _comment_block(line: str, count: int, newline: str = "\n") -> str:
    return (line + newline) * count


def make_case_files(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    cases: dict[str, Path] = {}

    cases["F1_short_comments"] = root / "f1_short_comments.py"
    cases["F1_short_comments"].write_text(
        _comment_block("# short", 12000) + "pass\n",
        encoding="utf-8",
    )

    long_comment = "# " + ("abcdefghij" * 24)
    cases["F2_long_comments"] = root / "f2_long_comments.py"
    cases["F2_long_comments"].write_text(
        _comment_block(long_comment, 5000) + "pass\n",
        encoding="utf-8",
    )

    cases["F3_utf8_cookie_long_comments"] = root / "f3_utf8_cookie_long_comments.py"
    cases["F3_utf8_cookie_long_comments"].write_text(
        "#!/usr/bin/env python3\n"
        "# coding: utf-8\n"
        + _comment_block(long_comment, 4500)
        + "pass\n",
        encoding="utf-8",
    )

    latin1_comment = "# ol\xe1 " + ("z" * 200)
    cases["F4_latin1_cookie_long_comments"] = root / "f4_latin1_cookie_long_comments.py"
    cases["F4_latin1_cookie_long_comments"].write_bytes(
        (
            "# coding: latin-1\n"
            + _comment_block(latin1_comment, 4500)
            + "pass\n"
        ).encode("latin-1")
    )

    mixed_lines = []
    for i in range(3500):
        mixed_lines.append(f"v_{i} = {i}")
        if i % 50 == 0:
            mixed_lines.append(long_comment)
    cases["F5_mixed_module"] = root / "f5_mixed_module.py"
    cases["F5_mixed_module"].write_text("\n".join(mixed_lines) + "\n", encoding="utf-8")

    return cases


def bench_command(python: Path, script: Path) -> list[str]:
    return [str(python), "-S", "-B", str(script)]


def run_command_once(cmd: list[str], env: dict[str, str]) -> int:
    start = time.perf_counter_ns()
    subprocess.run(
        cmd,
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return time.perf_counter_ns() - start


def run_case(python: Path, script: Path, *, warmups: int, loops: int) -> dict[str, object]:
    env = benchmark_env()
    cmd = bench_command(python, script)
    for _ in range(warmups):
        run_command_once(cmd, env)
    samples = [run_command_once(cmd, env) for _ in range(loops)]
    return {
        "command": cmd,
        "warmups": warmups,
        "loops": loops,
        "samples_ns": samples,
        "mean_ns": statistics.fmean(samples),
        "median_ns": statistics.median(samples),
        "min_ns": min(samples),
        "max_ns": max(samples),
    }


def save_results(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def temporary_case_dir(prefix: str = "pegen-file-main-") -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix)
