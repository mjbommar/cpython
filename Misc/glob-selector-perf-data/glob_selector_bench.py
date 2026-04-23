from __future__ import annotations

import gc
import json
import shutil
import statistics
import sys
import tempfile
import timeit
from pathlib import Path


def make_tree(root: Path):
    flat = root / "flat"
    flat.mkdir()
    for i in range(80):
        (flat / f"f{i}.py").write_text("x=1\n")
        (flat / f"f{i}.txt").write_text("txt\n")

    for i in range(12):
        pkg = root / "tree" / f"pkg{i}" / "subpkg"
        pkg.mkdir(parents=True, exist_ok=True)
        for j in range(12):
            (pkg / f"m{j}.py").write_text(f"v={i*j}\n")
            (pkg / f"d{j}.dat").write_text("x\n")

    deep = root / "deep"
    for i in range(10):
        node = deep / f"l{i}" / f"leaf{i}"
        node.mkdir(parents=True, exist_ok=True)
        for j in range(6):
            (node / f"target{j}.py").write_text("x=1\n")
            (node / f"target{j}.txt").write_text("x\n")


def trimmed_mean(runs):
    ordered = sorted(runs)
    if len(ordered) <= 2:
        return statistics.mean(ordered)
    return statistics.mean(ordered[1:-1])


def bench(fn, repeat=7):
    fn()
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        runs = timeit.repeat(fn, number=1, repeat=repeat)
    finally:
        if gc_was_enabled:
            gc.enable()
    return {
        "runs": runs,
        "min": min(runs),
        "median": statistics.median(runs),
        "trimmed_mean": trimmed_mean(runs),
    }


tmp = Path(tempfile.mkdtemp(prefix="glob-bench-"))
make_tree(tmp)

FLAT = tmp / "flat"
TREE = tmp / "tree"
DEEP = tmp / "deep"


def setup_flat_star():
    root = FLAT

    def run():
        for _ in range(1500):
            list(root.glob("*"))

    return run


def setup_flat_py():
    root = FLAT

    def run():
        for _ in range(1500):
            list(root.glob("*.py"))

    return run


def setup_tree_py():
    root = TREE

    def run():
        for _ in range(300):
            list(root.rglob("*.py"))

    return run


def setup_tree_literal():
    root = TREE

    def run():
        for _ in range(1200):
            list(root.glob("pkg7/subpkg/*.py"))

    return run


def setup_deep_target():
    root = DEEP

    def run():
        for _ in range(500):
            list(root.rglob("target*.py"))

    return run


SCENARIOS = [
    ("G1_flat_star", setup_flat_star),
    ("G2_flat_py", setup_flat_py),
    ("G3_tree_py_recursive", setup_tree_py),
    ("G4_tree_literal", setup_tree_literal),
    ("G5_deep_target_recursive", setup_deep_target),
]


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    results = {"meta": {"label": label, "python": sys.version.split()[0]}}
    try:
        for name, setup in SCENARIOS:
            results[name] = bench(setup())
    finally:
        shutil.rmtree(tmp)
    if out:
        Path(out).write_text(json.dumps(results, indent=2, sort_keys=True))
    for name, _ in SCENARIOS:
        data = results[name]
        print(
            f"{name:24s} trimmed_mean={data['trimmed_mean']:.6f}s "
            f"min={data['min']:.6f}s"
        )


if __name__ == "__main__":
    main()
