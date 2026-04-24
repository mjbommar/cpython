#!/usr/bin/env python3
"""Guardrails for traceback stack/TracebackException format experiments."""

from __future__ import annotations

import pathlib
import re
import tempfile
import textwrap
import traceback


_TMPDIR = tempfile.TemporaryDirectory(prefix="traceback-stack-guardrail-")
_ORIGINAL_TRACEBACKEXCEPTION_FORMAT = traceback.TracebackException.format
_ORIGINAL_STACKSUMMARY_FORMAT = traceback.StackSummary.format


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


def _candidate_te_format_simple(self, *, chain=True, _ctx=None, **kwargs):
    colorize = kwargs.get("colorize", False)
    if (
        _ctx is None
        and chain
        and self.__cause__ is None
        and self.__context__ is None
        and self.exceptions is None
    ):
        local_ctx = traceback._ExceptionPrintContext()
        if self.stack:
            yield from local_ctx.emit("Traceback (most recent call last):\n")
            yield from local_ctx.emit(self.stack.format(colorize=colorize))
        yield from local_ctx.emit(self.format_exception_only(colorize=colorize))
        return
    yield from _ORIGINAL_TRACEBACKEXCEPTION_FORMAT(self, chain=chain, _ctx=_ctx, **kwargs)


def _candidate_stack_format_no_repeats(self, **kwargs):
    colorize = kwargs.get("colorize", False)
    result = []
    append = result.append
    format_frame_summary = self.format_frame_summary
    recursive_cutoff = traceback._RECURSIVE_CUTOFF
    it = iter(self)

    for frame_summary in it:
        formatted_frame = format_frame_summary(frame_summary, colorize=colorize)
        if formatted_frame is None:
            continue
        append(formatted_frame)
        last_file = frame_summary.filename
        last_line = frame_summary.lineno
        last_name = frame_summary.name
        count = 1
        break
    else:
        return result

    def finish_slow(start_frame, start_formatted):
        nonlocal last_file, last_line, last_name, count

        frame_summary = start_frame
        formatted_frame = start_formatted
        while True:
            if (
                last_file != frame_summary.filename or
                last_line != frame_summary.lineno or
                last_name != frame_summary.name
            ):
                if count > recursive_cutoff:
                    repeat = count - recursive_cutoff
                    append(
                        f'  [Previous line repeated {repeat} more '
                        f'time{"s" if repeat > 1 else ""}]\n'
                    )
                last_file = frame_summary.filename
                last_line = frame_summary.lineno
                last_name = frame_summary.name
                count = 0
            count += 1
            if count <= recursive_cutoff:
                append(formatted_frame)

            for frame_summary in it:
                formatted_frame = format_frame_summary(frame_summary, colorize=colorize)
                if formatted_frame is None:
                    continue
                break
            else:
                if count > recursive_cutoff:
                    repeat = count - recursive_cutoff
                    append(
                        f'  [Previous line repeated {repeat} more '
                        f'time{"s" if repeat > 1 else ""}]\n'
                    )
                return result

    for frame_summary in it:
        formatted_frame = format_frame_summary(frame_summary, colorize=colorize)
        if formatted_frame is None:
            continue
        if (
            last_file == frame_summary.filename and
            last_line == frame_summary.lineno and
            last_name == frame_summary.name
        ):
            return finish_slow(frame_summary, formatted_frame)
        append(formatted_frame)
        last_file = frame_summary.filename
        last_line = frame_summary.lineno
        last_name = frame_summary.name

    return result


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
    chain_ns = _build_namespace(
        "tb_chain.py",
        """
        def trigger():
            try:
                raise KeyError("inner")
            except KeyError as exc:
                raise ValueError("outer") from exc
        """,
    )

    cases = {
        "simple": _capture_exception(simple_ns["trigger"]),
        "locals": _capture_exception(locals_ns["trigger"]),
        "caret": _capture_exception(caret_ns["trigger"]),
        "recursive": _capture_exception(recursive_ns["trigger"]),
        "chain": _capture_exception(chain_ns["trigger"]),
    }

    expected = {}
    for key, exc in cases.items():
        te = traceback.TracebackException.from_exception(
            exc,
            capture_locals=(key == "locals"),
        )
        expected[key] = _normalize("".join(te.format()))

    traceback.TracebackException.format = _candidate_te_format_simple
    try:
        actual = {}
        for key, exc in cases.items():
            te = traceback.TracebackException.from_exception(
                exc,
                capture_locals=(key == "locals"),
            )
            actual[key] = _normalize("".join(te.format()))
    finally:
        traceback.TracebackException.format = _ORIGINAL_TRACEBACKEXCEPTION_FORMAT

    for key in expected:
        assert actual[key] == expected[key], key

    traceback.StackSummary.format = _candidate_stack_format_no_repeats
    try:
        stack_actual = {}
        for key, exc in cases.items():
            te = traceback.TracebackException.from_exception(
                exc,
                capture_locals=(key == "locals"),
            )
            stack_actual[key] = _normalize("".join(te.format()))
    finally:
        traceback.StackSummary.format = _ORIGINAL_STACKSUMMARY_FORMAT

    for key in expected:
        assert stack_actual[key] == expected[key], key

    assert "ValueError: boom\n" in actual["simple"]
    assert "alpha = 10" in actual["locals"]
    assert "^" in actual["caret"] or "~" in actual["caret"]
    assert "[Previous line repeated" in actual["recursive"]
    assert "The above exception was the direct cause of the following exception:\n" in actual["chain"]

    print("traceback stack format guardrails: ok")


if __name__ == "__main__":
    main()
