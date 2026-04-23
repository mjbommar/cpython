from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


failures = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    line = f"{tag}  {name}" + (f"  -- {detail}" if detail else "")
    print(line)
    if not cond:
        failures.append(name)


def make_tree(root: Path):
    (root / "flat").mkdir()
    (root / "flat" / "a.py").write_text("a=1\n")
    (root / "flat" / "b.txt").write_text("b\n")
    (root / "flat" / ".hidden.py").write_text("h=1\n")

    for i in range(8):
        pkg = root / "tree" / f"pkg{i}" / "subpkg"
        pkg.mkdir(parents=True, exist_ok=True)
        for j in range(6):
            (pkg / f"m{j}.py").write_text(f"v={i*j}\n")
            (pkg / f"d{j}.dat").write_text("x\n")

    deep = root / "deep"
    for i in range(5):
        node = deep / f"l{i}" / f"leaf{i}"
        node.mkdir(parents=True, exist_ok=True)
        (node / "target.py").write_text("x=1\n")


tmp = Path(tempfile.mkdtemp(prefix="glob-guard-"))
try:
    make_tree(tmp)

    flat_star = sorted(p.name for p in (tmp / "flat").glob("*"))
    check("flat_star", flat_star == [".hidden.py", "a.py", "b.txt"])

    flat_py = sorted(p.name for p in (tmp / "flat").glob("*.py"))
    check("flat_py", flat_py == [".hidden.py", "a.py"])

    recursive_py = sorted((tmp / "tree").rglob("*.py"))
    check("recursive_py_count", len(recursive_py) == 48, f"count={len(recursive_py)}")

    deep_target = sorted((tmp / "deep").rglob("target.py"))
    check("deep_target_count", len(deep_target) == 5, f"count={len(deep_target)}")

    literal_nested = sorted((tmp / "tree").glob("pkg3/subpkg/*.py"))
    check("literal_nested", len(literal_nested) == 6, f"count={len(literal_nested)}")
finally:
    shutil.rmtree(tmp)

if failures:
    print(f"FAILED {len(failures)} checks: {', '.join(failures)}")
    sys.exit(1)
print("all glob selector guardrails passed")
