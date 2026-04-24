#!/usr/bin/env python3
"""Focused benchmark for recursive glob selector ideas."""

from __future__ import annotations

import argparse
import glob
import json
import pathlib
import shutil
import statistics
import sys
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


def build_tree(root: pathlib.Path) -> None:
    for depth in range(4):
        base = root / f"pkg{depth}"
        (base / "suba").mkdir(parents=True, exist_ok=True)
        (base / "subb").mkdir(parents=True, exist_ok=True)
        (base / f"mod{depth}.py").write_text("x = 1\n")
        (base / f"data{depth}.txt").write_text("data\n")
        (base / "suba" / f"inner{depth}.py").write_text("y = 2\n")
        (base / "suba" / f"inner{depth}.md").write_text("doc\n")
        (base / "subb" / f"leaf{depth}.py").write_text("z = 3\n")
        (base / "subb" / f"leaf{depth}.bin").write_bytes(b"\0\1")
    deep = root / "deep"
    current = deep
    for i in range(12):
        current.mkdir(parents=True, exist_ok=True)
        (current / f"n{i}.py").write_text("n = 1\n")
        current = current / f"d{i}"
    current.mkdir(parents=True, exist_ok=True)
    (current / "tail.txt").write_text("tail\n")


class Variant:
    def __init__(self, variant: str) -> None:
        self.variant = variant

    def __enter__(self):
        if self.variant != "baseline":
            install_candidate(self.variant)
        return self

    def __exit__(self, exc_type, exc, tb):
        restore_original()
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "lazy_stringify", "inline_step"),
        default="baseline",
    )
    parser.add_argument("--loops", type=int, default=250)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="perf-glob-"))
    try:
        build_tree(tmp)
        p = pathlib.Path(tmp)
        with Variant(ns.variant):
            results = {
                "variant": ns.variant,
                "G1_glob_recursive_all": measure(
                    "glob_recursive_all",
                    lambda: list(glob.iglob(str(tmp / "**" / "*"), recursive=True)),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "G2_glob_recursive_py": measure(
                    "glob_recursive_py",
                    lambda: list(glob.iglob(str(tmp / "**" / "*.py"), recursive=True)),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "G3_pathlib_rglob_all": measure(
                    "pathlib_rglob_all",
                    lambda: list(p.rglob("*")),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "G4_pathlib_glob_recursive_all": measure(
                    "pathlib_glob_recursive_all",
                    lambda: list(p.glob("**/*")),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
                "G5_pathlib_glob_recursive_py": measure(
                    "pathlib_glob_recursive_py",
                    lambda: list(p.glob("**/*.py")),
                    loops=ns.loops,
                    repeat=ns.repeat,
                ),
            }
    finally:
        shutil.rmtree(tmp)

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "G1_glob_recursive_all",
        "G2_glob_recursive_py",
        "G3_pathlib_rglob_all",
        "G4_pathlib_glob_recursive_all",
        "G5_pathlib_glob_recursive_py",
    ):
        data = results[key]
        print(f"{key}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
