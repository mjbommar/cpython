#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys
import textwrap


def run(python: pathlib.Path, source: str, filename: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONHASHSEED", "0")
    env["PYTHON_COMPILE_PHASE_STATS"] = "1"
    child = textwrap.dedent(
        f"""
        src = {source!r}
        code = compile(src, {filename!r}, "exec")
        ns = {{}}
        exec(code, ns, ns)
        """
    )
    return subprocess.run(
        [str(python), "-S", "-c", child],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=pathlib.Path, default=pathlib.Path("./python"))
    ns = parser.parse_args()
    python = ns.python.resolve()

    proc = run(
        python,
        "x = 1\nprint(x + 2)\n",
        "[perf-compile]module",
    )
    assert proc.stdout == "3\n", proc.stdout
    assert "compile-phase\tfilename=[perf-compile]module\t" in proc.stderr, proc.stderr

    proc = run(
        python,
        "def outer(x):\n"
        "    def inner(y):\n"
        "        return x + y\n"
        "    print(inner(5))\n"
        "outer(7)\n",
        "[perf-compile]nested",
    )
    assert proc.stdout == "12\n", proc.stdout
    assert "compile-phase\tfilename=[perf-compile]nested\t" in proc.stderr, proc.stderr

    proc = run(
        python,
        "class C:\n"
        "    x = 4\n"
        "    def f(self):\n"
        "        return self.x\n"
        "print(C().f())\n",
        "plain-filename",
    )
    assert proc.stdout == "4\n", proc.stdout
    assert "compile-phase\t" not in proc.stderr, proc.stderr

    print("compile phase attribution semantics: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
