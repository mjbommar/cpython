#!/usr/bin/env python3
"""Guardrails for marshal code-object load fast-path experiments."""

from __future__ import annotations

import importlib._bootstrap_external as _bootstrap_external
import marshal
import textwrap


def _make_payload(filename: str, source: str) -> tuple[object, bytes]:
    code = compile(textwrap.dedent(source), filename, "exec")
    return code, marshal.dumps(code)


def _exec(code):
    namespace: dict[str, object] = {}
    exec(code, namespace)
    return namespace


def main() -> None:
    cases = {
        "tiny": (
            "tiny.py",
            """
            value = 1
            answer = value + 41
            """,
            "answer",
            42,
        ),
        "nested": (
            "nested.py",
            """
            def outer(a):
                factor = 3
                def inner(b):
                    return a * factor + b
                return inner(5)

            result = outer(7)
            """,
            "result",
            26,
        ),
        "many_consts": (
            "many_consts.py",
            """
            TABLE = {
                "aa": 1, "ab": 2, "ac": 3, "ad": 4, "ae": 5, "af": 6, "ag": 7,
                "ba": 8, "bb": 9, "bc": 10, "bd": 11, "be": 12, "bf": 13, "bg": 14,
                "ca": 15, "cb": 16, "cc": 17, "cd": 18, "ce": 19, "cf": 20, "cg": 21,
            }

            def lookup(key):
                return TABLE.get(key, -1)

            result = lookup("cf")
            """,
            "result",
            20,
        ),
        "class_methods": (
            "class_methods.py",
            """
            class Greeter:
                prefix = "hello"

                def __init__(self, name):
                    self.name = name

                def render(self):
                    return f"{self.prefix}, {self.name}"

            greeting = Greeter("world").render()
            """,
            "greeting",
            "hello, world",
        ),
    }

    for name, (filename, source, key, expected) in cases.items():
        code, payload = _make_payload(filename, source)

        loaded = marshal.loads(payload)
        assert isinstance(loaded, type(code)), name
        assert marshal.dumps(loaded) == payload, name
        assert _exec(loaded)[key] == expected, name

        compiled = _bootstrap_external._compile_bytecode(
            payload,
            name=name,
            bytecode_path=f"{name}.pyc",
            source_path=f"/tmp/{filename}",
        )
        assert isinstance(compiled, type(code)), name
        assert compiled.co_filename == f"/tmp/{filename}", name
        assert _exec(compiled)[key] == expected, name

    print("marshal code load guardrails: ok")


if __name__ == "__main__":
    main()
