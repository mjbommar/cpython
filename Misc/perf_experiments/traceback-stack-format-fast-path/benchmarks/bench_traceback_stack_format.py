#!/usr/bin/env python3
"""Focused benchmark for traceback stack/TracebackException format ideas."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import tempfile
import textwrap
import time
import traceback


_TMPDIR = tempfile.TemporaryDirectory(prefix="perf-traceback-stack-format-")


def _build_namespace(filename: str, source: str) -> dict[str, object]:
    path = pathlib.Path(_TMPDIR.name, filename)
    path.write_text(textwrap.dedent(source))
    namespace: dict[str, object] = {}
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    return namespace


def _capture_exception(fn):
    try:
        fn()
    except Exception as exc:  # pragma: no cover - exercised by benchmark setup
        return exc
    raise AssertionError("expected exception")


def _capture_cases() -> dict[str, object]:
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

    simple_exc = _capture_exception(simple_ns["trigger"])
    locals_exc = _capture_exception(locals_ns["trigger"])
    caret_exc = _capture_exception(caret_ns["trigger"])
    recursive_exc = _capture_exception(recursive_ns["trigger"])
    chain_exc = _capture_exception(chain_ns["trigger"])

    return {
        "simple_exc": simple_exc,
        "locals_exc": locals_exc,
        "caret_exc": caret_exc,
        "recursive_exc": recursive_exc,
        "chain_exc": chain_exc,
        "simple_te": traceback.TracebackException.from_exception(simple_exc, capture_locals=False),
        "locals_te": traceback.TracebackException.from_exception(locals_exc, capture_locals=True),
        "caret_te": traceback.TracebackException.from_exception(caret_exc, capture_locals=False),
        "recursive_te": traceback.TracebackException.from_exception(recursive_exc, capture_locals=False),
        "chain_te": traceback.TracebackException.from_exception(chain_exc, capture_locals=False),
    }


CASES = _capture_cases()

_ORIGINAL_TRACEBACKEXCEPTION_FORMAT = traceback.TracebackException.format
_ORIGINAL_STACKSUMMARY_FORMAT = traceback.StackSummary.format


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


class Variant:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        if self.name == "runtime":
            return
        if self.name == "te_simple_fastpath":
            traceback.TracebackException.format = _candidate_te_format_simple
            return
        if self.name == "stack_no_repeats":
            traceback.StackSummary.format = _candidate_stack_format_no_repeats
            return
        raise ValueError(f"unknown variant: {self.name}")

    def __exit__(self, exc_type, exc, tb):
        traceback.TracebackException.format = _ORIGINAL_TRACEBACKEXCEPTION_FORMAT
        traceback.StackSummary.format = _ORIGINAL_STACKSUMMARY_FORMAT


def _stack_format_simple() -> list[str]:
    return CASES["simple_te"].stack.format()


def _stack_format_recursive() -> list[str]:
    return CASES["recursive_te"].stack.format()


def _te_simple() -> list[str]:
    return list(CASES["simple_te"].format())


def _te_locals() -> list[str]:
    return list(CASES["locals_te"].format())


def _te_caret() -> list[str]:
    return list(CASES["caret_te"].format())


def _te_chain() -> list[str]:
    return list(CASES["chain_te"].format())


def _format_exception_simple() -> list[str]:
    return traceback.format_exception(CASES["simple_exc"])


def _format_exception_caret() -> list[str]:
    return traceback.format_exception(CASES["caret_exc"])


BENCHES = {
    "T1_stack_simple": ("stack simple", _stack_format_simple),
    "T2_stack_recursive": ("stack recursive", _stack_format_recursive),
    "T3_te_simple": ("TracebackException.format simple", _te_simple),
    "T4_te_locals": ("TracebackException.format locals", _te_locals),
    "T5_te_caret": ("TracebackException.format caret", _te_caret),
    "T6_te_chain": ("TracebackException.format chain", _te_chain),
    "T7_format_exception_simple": ("traceback.format_exception simple", _format_exception_simple),
    "T8_format_exception_caret": ("traceback.format_exception caret", _format_exception_caret),
}


def measure(label: str, func, *, loops: int, repeat: int) -> dict[str, object]:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        for _ in range(loops):
            func()
        elapsed = time.perf_counter() - start
        samples.append(elapsed / loops)
    return {
        "label": label,
        "loops": loops,
        "repeat": repeat,
        "samples_ns": [round(sample * 1e9, 1) for sample in samples],
        "best_ns": round(min(samples) * 1e9, 1),
        "mean_ns": round(statistics.mean(samples) * 1e9, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("runtime", "te_simple_fastpath", "stack_no_repeats"),
        default="runtime",
    )
    parser.add_argument("--loops-stack", type=int, default=8_000)
    parser.add_argument("--loops-te", type=int, default=6_000)
    parser.add_argument("--loops-format-exc", type=int, default=4_000)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
            "T1_stack_simple": measure(*BENCHES["T1_stack_simple"], loops=ns.loops_stack, repeat=ns.repeat),
            "T2_stack_recursive": measure(*BENCHES["T2_stack_recursive"], loops=ns.loops_stack, repeat=ns.repeat),
            "T3_te_simple": measure(*BENCHES["T3_te_simple"], loops=ns.loops_te, repeat=ns.repeat),
            "T4_te_locals": measure(*BENCHES["T4_te_locals"], loops=ns.loops_te, repeat=ns.repeat),
            "T5_te_caret": measure(*BENCHES["T5_te_caret"], loops=ns.loops_te, repeat=ns.repeat),
            "T6_te_chain": measure(*BENCHES["T6_te_chain"], loops=ns.loops_te, repeat=ns.repeat),
            "T7_format_exception_simple": measure(
                *BENCHES["T7_format_exception_simple"], loops=ns.loops_format_exc, repeat=ns.repeat
            ),
            "T8_format_exception_caret": measure(
                *BENCHES["T8_format_exception_caret"], loops=ns.loops_format_exc, repeat=ns.repeat
            ),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in (
        "T1_stack_simple",
        "T2_stack_recursive",
        "T3_te_simple",
        "T4_te_locals",
        "T5_te_caret",
        "T6_te_chain",
        "T7_format_exception_simple",
        "T8_format_exception_caret",
    ):
        result = results[key]
        print(
            f"{result['label']}: best={result['best_ns']} ns "
            f"mean={result['mean_ns']} ns samples={result['samples_ns']}"
        )


if __name__ == "__main__":
    main()
