#!/usr/bin/env python3
"""Guardrails for recursive glob selector candidates."""

from __future__ import annotations

import glob
import pathlib
import shutil
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


def build_tree(root: pathlib.Path) -> None:
    (root / "pkg" / "sub").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("x = 1\n")
    (root / "pkg" / "note.txt").write_text("note\n")
    (root / "pkg" / "sub" / "leaf.py").write_text("y = 2\n")
    (root / "pkg" / "sub" / "leaf.txt").write_text("txt\n")
    (root / "other").mkdir()
    (root / "other" / "z.py").write_text("z = 3\n")


def collect(root: pathlib.Path):
    p = pathlib.Path(root)
    return {
        "glob_all": sorted(glob.iglob(str(root / "**" / "*"), recursive=True)),
        "glob_py": sorted(glob.iglob(str(root / "**" / "*.py"), recursive=True)),
        "pathlib_rglob_all": sorted(str(x) for x in p.rglob("*")),
        "pathlib_glob_all": sorted(str(x) for x in p.glob("**/*")),
        "pathlib_glob_py": sorted(str(x) for x in p.glob("**/*.py")),
    }


def main() -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="guard-glob-"))
    try:
        build_tree(tmp)
        baseline = collect(tmp)
        install_candidate("inline_step")
        try:
            candidate = collect(tmp)
        finally:
            restore_original()
        assert baseline == candidate, (baseline, candidate)
    finally:
        shutil.rmtree(tmp)
    print("glob recursive selector guardrails: ok")


if __name__ == "__main__":
    main()
