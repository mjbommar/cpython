#!/usr/bin/env python3
"""Guardrails for traceback formatting fast-path experiments."""

from __future__ import annotations

import re
import pathlib
import tempfile
import textwrap
import traceback


_TMPDIR = tempfile.TemporaryDirectory(prefix="traceback-guardrail-")


def _build_namespace(filename: str, source: str) -> dict[str, object]:
    path = pathlib.Path(_TMPDIR.name, filename)
    path.write_text(textwrap.dedent(source))
    namespace: dict[str, object] = {}
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    return namespace


def _capture_exception(fn):
    try:
        fn()
    except Exception as exc:  # pragma: no cover - exercised by guardrail setup
        return exc
    raise AssertionError("expected exception")


def _normalize(text: str) -> str:
    text = re.sub(r"line \d+", "line <N>", text)
    text = re.sub(r"(/[^\n\"]*/)?tb_", "tb_", text)
    text = text.replace("\r\n", "\n")
    return text


def main() -> None:
    simple_ns = _build_namespace(
        "tb_simple.py",
        """
        def trigger():
            token = 1
            raise ValueError("boom")
        """,
    )
    locals_ns = _build_namespace(
        "tb_locals.py",
        """
        def trigger():
            alpha = 10
            beta = {"key": "value"}
            raise RuntimeError("locals")
        """,
    )
    caret_ns = _build_namespace(
        "tb_caret.py",
        """
        def trigger():
            left = 10
            right = 0
            return (left +
                    20) / right
        """,
    )
    recursive_ns = _build_namespace(
        "tb_recursive.py",
        """
        def recur(n):
            if n:
                return recur(n - 1)
            raise LookupError("deep")

        def trigger():
            recur(6)
        """,
    )

    simple_exc = _capture_exception(simple_ns["trigger"])
    locals_exc = _capture_exception(locals_ns["trigger"])
    caret_exc = _capture_exception(caret_ns["trigger"])
    recursive_exc = _capture_exception(recursive_ns["trigger"])

    simple_te = traceback.TracebackException.from_exception(simple_exc, capture_locals=False)
    locals_te = traceback.TracebackException.from_exception(locals_exc, capture_locals=True)
    caret_te = traceback.TracebackException.from_exception(caret_exc, capture_locals=False)
    recursive_te = traceback.TracebackException.from_exception(recursive_exc, capture_locals=False)

    simple_frame = _normalize(simple_te.stack.format_frame_summary(simple_te.stack[-1]))
    assert 'File "tb_simple.py", line <N>, in trigger' in simple_frame
    assert 'raise ValueError("boom")' in simple_frame
    assert "token = 1" not in simple_frame

    locals_frame = _normalize(locals_te.stack.format_frame_summary(locals_te.stack[-1]))
    assert 'File "tb_locals.py", line <N>, in trigger' in locals_frame
    assert 'raise RuntimeError("locals")' in locals_frame
    assert "alpha = 10" in locals_frame
    assert "beta = {'key': 'value'}" in locals_frame

    caret_frame = _normalize(caret_te.stack.format_frame_summary(caret_te.stack[-1]))
    assert 'File "tb_caret.py", line <N>, in trigger' in caret_frame
    assert "return (left +" in caret_frame
    assert "^" in caret_frame or "~" in caret_frame

    recursive_stack = "".join(recursive_te.stack.format())
    assert "[Previous line repeated" in recursive_stack

    simple_exc_text = _normalize("".join(simple_te.format()))
    assert simple_exc_text.endswith("ValueError: boom\n")
    assert "token = 1" not in simple_exc_text

    locals_exc_text = _normalize("".join(locals_te.format()))
    assert locals_exc_text.endswith("RuntimeError: locals\n")
    assert "alpha = 10" in locals_exc_text

    caret_exc_text = _normalize("".join(traceback.format_exception(caret_exc)))
    assert caret_exc_text.endswith("ZeroDivisionError: division by zero\n")
    assert 'File "tb_caret.py", line <N>, in trigger' in caret_exc_text
    assert "^" in caret_exc_text or "~" in caret_exc_text

    print("traceback format guardrails: ok")


if __name__ == "__main__":
    main()
