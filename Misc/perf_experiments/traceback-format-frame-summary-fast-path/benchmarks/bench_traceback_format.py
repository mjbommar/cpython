#!/usr/bin/env python3
"""Focused benchmark for traceback formatting fast-path ideas."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import tempfile
import textwrap
import time
import traceback


_TMPDIR = tempfile.TemporaryDirectory(prefix="perf-traceback-format-")


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

    simple_exc = _capture_exception(simple_ns["trigger"])
    locals_exc = _capture_exception(locals_ns["trigger"])
    caret_exc = _capture_exception(caret_ns["trigger"])
    recursive_exc = _capture_exception(recursive_ns["trigger"])

    simple_te = traceback.TracebackException.from_exception(simple_exc, capture_locals=False)
    locals_te = traceback.TracebackException.from_exception(locals_exc, capture_locals=True)
    caret_te = traceback.TracebackException.from_exception(caret_exc, capture_locals=False)
    recursive_te = traceback.TracebackException.from_exception(recursive_exc, capture_locals=False)

    return {
        "simple_exc": simple_exc,
        "locals_exc": locals_exc,
        "caret_exc": caret_exc,
        "recursive_exc": recursive_exc,
        "simple_te": simple_te,
        "locals_te": locals_te,
        "caret_te": caret_te,
        "recursive_te": recursive_te,
        "simple_frame": simple_te.stack[-1],
        "locals_frame": locals_te.stack[-1],
        "caret_frame": caret_te.stack[-1],
    }


CASES = _capture_cases()


def _format_frame_simple() -> str:
    return CASES["simple_te"].stack.format_frame_summary(CASES["simple_frame"])


def _format_frame_locals() -> str:
    return CASES["locals_te"].stack.format_frame_summary(CASES["locals_frame"])


def _format_frame_caret() -> str:
    return CASES["caret_te"].stack.format_frame_summary(CASES["caret_frame"])


def _stack_format_simple() -> list[str]:
    return CASES["simple_te"].stack.format()


def _stack_format_recursive() -> list[str]:
    return CASES["recursive_te"].stack.format()


def _tracebackexception_format_simple() -> list[str]:
    return list(CASES["simple_te"].format())


def _tracebackexception_format_caret() -> list[str]:
    return list(CASES["caret_te"].format())


def _tracebackexception_format_locals() -> list[str]:
    return list(CASES["locals_te"].format())


def _format_exception_simple() -> list[str]:
    return traceback.format_exception(CASES["simple_exc"])


def _format_exception_caret() -> list[str]:
    return traceback.format_exception(CASES["caret_exc"])


BENCHES = {
    "T1_frame_simple": ("frame simple", _format_frame_simple),
    "T2_frame_locals": ("frame with locals", _format_frame_locals),
    "T3_frame_caret": ("frame with caret data", _format_frame_caret),
    "T4_stack_simple": ("stack format simple", _stack_format_simple),
    "T5_stack_recursive": ("stack format recursive", _stack_format_recursive),
    "T6_te_simple": ("TracebackException.format simple", _tracebackexception_format_simple),
    "T7_te_caret": ("TracebackException.format caret", _tracebackexception_format_caret),
    "T8_te_locals": ("TracebackException.format locals", _tracebackexception_format_locals),
    "T9_format_exception_simple": ("traceback.format_exception simple", _format_exception_simple),
    "T10_format_exception_caret": ("traceback.format_exception caret", _format_exception_caret),
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
    parser.add_argument("--loops-frame", type=int, default=20_000)
    parser.add_argument("--loops-stack", type=int, default=8_000)
    parser.add_argument("--loops-te", type=int, default=6_000)
    parser.add_argument("--loops-format-exc", type=int, default=4_000)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    results = {
        "T1_frame_simple": measure(*BENCHES["T1_frame_simple"], loops=ns.loops_frame, repeat=ns.repeat),
        "T2_frame_locals": measure(*BENCHES["T2_frame_locals"], loops=ns.loops_frame, repeat=ns.repeat),
        "T3_frame_caret": measure(*BENCHES["T3_frame_caret"], loops=ns.loops_frame, repeat=ns.repeat),
        "T4_stack_simple": measure(*BENCHES["T4_stack_simple"], loops=ns.loops_stack, repeat=ns.repeat),
        "T5_stack_recursive": measure(*BENCHES["T5_stack_recursive"], loops=ns.loops_stack, repeat=ns.repeat),
        "T6_te_simple": measure(*BENCHES["T6_te_simple"], loops=ns.loops_te, repeat=ns.repeat),
        "T7_te_caret": measure(*BENCHES["T7_te_caret"], loops=ns.loops_te, repeat=ns.repeat),
        "T8_te_locals": measure(*BENCHES["T8_te_locals"], loops=ns.loops_te, repeat=ns.repeat),
        "T9_format_exception_simple": measure(
            *BENCHES["T9_format_exception_simple"], loops=ns.loops_format_exc, repeat=ns.repeat
        ),
        "T10_format_exception_caret": measure(
            *BENCHES["T10_format_exception_caret"], loops=ns.loops_format_exc, repeat=ns.repeat
        ),
    }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    for key in (
        "T1_frame_simple",
        "T2_frame_locals",
        "T3_frame_caret",
        "T4_stack_simple",
        "T5_stack_recursive",
        "T6_te_simple",
        "T7_te_caret",
        "T8_te_locals",
        "T9_format_exception_simple",
        "T10_format_exception_caret",
    ):
        result = results[key]
        print(
            f"{result['label']}: best={result['best_ns']} ns "
            f"mean={result['mean_ns']} ns samples={result['samples_ns']}"
        )


if __name__ == "__main__":
    main()
