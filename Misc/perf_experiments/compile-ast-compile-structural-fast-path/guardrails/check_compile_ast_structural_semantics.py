#!/usr/bin/env python3
from __future__ import annotations

import ast


def main() -> int:
    ns: dict[str, object] = {}

    code = compile(ast.parse("x = 1\ny = x + 2\n"), "<guardrail>", "exec")
    exec(code, ns)
    assert ns["x"] == 1
    assert ns["y"] == 3

    ns = {}
    code = compile(
        ast.parse(
            "def outer(x):\n"
            "    y = x + 1\n"
            "    def inner(z):\n"
            "        return y + z\n"
            "    return inner\n"
        ),
        "<guardrail>",
        "exec",
    )
    exec(code, ns)
    outer = ns["outer"]
    inner = outer(10)
    assert outer.__qualname__ == "outer"
    assert inner.__qualname__ == "outer.<locals>.inner"
    assert inner(5) == 16

    ns = {}
    code = compile(
        ast.parse(
            "class C:\n"
            "    scale = 3\n"
            "    def f(self, x):\n"
            "        return self.scale + x\n"
        ),
        "<guardrail>",
        "exec",
    )
    exec(code, ns)
    C = ns["C"]
    assert C.__qualname__ == "C"
    assert C().f(5) == 8

    ns = {}
    code = compile(ast.parse("result = [x * 2 for x in range(6) if x % 2]\n"), "<guardrail>", "exec")
    exec(code, ns)
    assert ns["result"] == [2, 6, 10]

    print("compile ast structural semantics: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
