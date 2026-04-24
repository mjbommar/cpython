#!/usr/bin/env python3
"""Guardrails for pegen string-entry fast-path experiments."""

from __future__ import annotations

import ast
import codeop
import symtable
import textwrap


def main() -> None:
    exec_src = "x = 1\ny = x + 41\n"
    code = compile(exec_src, "<guard>", "exec")
    namespace: dict[str, object] = {}
    exec(code, namespace)
    assert namespace["y"] == 42

    eval_code = compile("1 + 2 + 3 + 4", "<guard>", "eval")
    assert eval(eval_code, {}) == 10

    tree = ast.parse(
        textwrap.dedent(
            """
            value = []  # type: list[int]
            other = 3   # type: int
            """
        ),
        filename="<guard>",
        mode="exec",
        type_comments=True,
    )
    assert tree.body[0].type_comment == "list[int]"
    assert tree.body[1].type_comment == "int"

    module = compile("x = 5\n", "<guard>", "exec", ast.PyCF_ONLY_AST)
    assert isinstance(module, ast.Module)
    assert module.body[0].targets[0].id == "x"

    assert codeop.compile_command("if True:\n", filename="<guard>", symbol="exec") is None

    table = symtable.symtable("def f(x):\n    return x + 1\n", "<guard>", "exec")
    func = table.lookup("f").get_namespace()
    assert func.lookup("x").is_parameter()

    print("pegen string entry guardrails: ok")


if __name__ == "__main__":
    main()
