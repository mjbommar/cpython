#!/usr/bin/env python3
"""Focused benchmark for os.makedirs common-case fast-path ideas."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import statistics
import sys
import tempfile
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


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


def case_leaf_default(root):
    parent = os.path.join(root, "parent")
    os.mkdir(parent)
    leaf = os.path.join(parent, "leaf")

    def run():
        os.makedirs(leaf)
        os.rmdir(leaf)

    return run


def case_leaf_exist_ok(root):
    parent = os.path.join(root, "parent")
    os.mkdir(parent)
    leaf = os.path.join(parent, "leaf")

    def run():
        os.makedirs(leaf, exist_ok=True)
        os.rmdir(leaf)

    return run


def case_nested_default(root):
    top = os.path.join(root, "top")
    path = os.path.join(top, "a", "b", "c")

    def run():
        os.makedirs(path)
        shutil.rmtree(top)

    return run


def case_bytes_leaf(root):
    parent = os.path.join(root, "parent")
    os.mkdir(parent)
    leaf = os.fsencode(os.path.join(parent, "leaf"))
    leaf_str = os.path.join(parent, "leaf")

    def run():
        os.makedirs(leaf)
        os.rmdir(leaf_str)

    return run


def case_existing_dir_exist_ok(root):
    path = os.path.join(root, "existing")
    os.mkdir(path)

    def run():
        os.makedirs(path, exist_ok=True)

    return run


def build_cases():
    factories = [
        ("M1_leaf_default", case_leaf_default, 1000),
        ("M2_leaf_exist_ok_missing", case_leaf_exist_ok, 1000),
        ("M3_nested_default", case_nested_default, 350),
        ("M4_bytes_leaf_default", case_bytes_leaf, 1000),
        ("M5_existing_dir_exist_ok", case_existing_dir_exist_ok, 1800),
    ]
    built = []
    for label, factory, loops in factories:
        root = tempfile.mkdtemp(prefix=f"bench-os-makedirs-{label}-")
        built.append((label, factory(root), loops, root))
    return built


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("baseline", "mkdir_first"),
        default="baseline",
    )
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    cases = build_cases()
    try:
        with Variant(ns.variant):
            results = {"variant": ns.variant}
            for label, func, loops, _root in cases:
                results[label] = measure(label, func, loops=loops, repeat=ns.repeat)
    finally:
        for _label, _func, _loops, root in cases:
            shutil.rmtree(root, ignore_errors=True)

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for label in (
        "M1_leaf_default",
        "M2_leaf_exist_ok_missing",
        "M3_nested_default",
        "M4_bytes_leaf_default",
        "M5_existing_dir_exist_ok",
    ):
        data = results[label]
        print(f"{label}: best={data['best_ns']:.1f} ns mean={data['mean_ns']:.1f} ns")


if __name__ == "__main__":
    main()
