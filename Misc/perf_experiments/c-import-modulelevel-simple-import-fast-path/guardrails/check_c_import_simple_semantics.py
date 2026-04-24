#!/usr/bin/env python3
"""Guardrails for C import-module-level fast-path experiments."""

from __future__ import annotations

import builtins
import sys


class FalseyFromlist:
    def __init__(self) -> None:
        self.calls = 0

    def __bool__(self) -> bool:
        self.calls += 1
        return False


def _plain_math():
    import math
    return math


def _dotted_email():
    import email.parser
    return email


def _from_email():
    from email import parser
    return parser


def main() -> None:
    math_mod = _plain_math()
    assert math_mod.__name__ == "math"
    assert builtins.__import__("math").__name__ == "math"

    email_mod = _dotted_email()
    assert email_mod.__name__ == "email"
    assert "email.parser" in sys.modules
    assert builtins.__import__("email.parser").__name__ == "email"

    parser_mod = _from_email()
    assert parser_mod.__name__ == "email.parser"
    returned = builtins.__import__("email", globals(), locals(), ("parser",), 0)
    assert returned.__name__ == "email"
    assert hasattr(returned, "parser")

    empty_tuple = builtins.__import__("math", globals(), locals(), (), 0)
    assert empty_tuple.__name__ == "math"

    falsey = FalseyFromlist()
    weird = builtins.__import__("math", globals(), locals(), falsey, 0)
    assert weird.__name__ == "math"
    assert falsey.calls == 1

    print("c import module-level guardrails: ok")


if __name__ == "__main__":
    main()
