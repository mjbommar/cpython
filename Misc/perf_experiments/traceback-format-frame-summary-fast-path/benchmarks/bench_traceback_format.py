#!/usr/bin/env python3
"""Focused benchmark for traceback formatting fast-path ideas."""

from __future__ import annotations

import argparse
import contextlib
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

_ORIGINAL_FORMAT_FRAME_SUMMARY = traceback.StackSummary.format_frame_summary
_ORIGINAL_STACK_FORMAT = traceback.StackSummary.format


def _candidate_format_frame_summary_no_color(self, frame_summary, **kwargs):
    if kwargs.get("colorize", False):
        return _ORIGINAL_FORMAT_FRAME_SUMMARY(self, frame_summary, **kwargs)

    filename = frame_summary.filename
    if filename.startswith("<stdin-") and filename.endswith(">"):
        filename = "<stdin>"

    row = [f'  File "{filename}", line {frame_summary.lineno}, in {frame_summary.name}\n']
    dedented_lines = frame_summary._dedented_lines
    if dedented_lines and dedented_lines.strip():
        if frame_summary.colno is None or frame_summary.end_colno is None:
            row.append(textwrap.indent(frame_summary.line, "    ") + "\n")
        else:
            all_lines_original = frame_summary._original_lines.splitlines()
            first_line = all_lines_original[0]
            last_line = all_lines_original[frame_summary.end_lineno - frame_summary.lineno]

            start_offset = traceback._byte_offset_to_character_offset(first_line, frame_summary.colno)
            end_offset = traceback._byte_offset_to_character_offset(last_line, frame_summary.end_colno)

            all_lines = dedented_lines.splitlines()[
                :frame_summary.end_lineno - frame_summary.lineno + 1
            ]

            dedent_characters = len(first_line) - len(all_lines[0])
            start_offset = max(0, start_offset - dedent_characters)
            end_offset = max(0, end_offset - dedent_characters)

            dp_start_offset = traceback._display_width(all_lines[0], offset=start_offset)
            dp_end_offset = traceback._display_width(all_lines[-1], offset=end_offset)

            segment = "\n".join(all_lines)
            segment = segment[start_offset:len(segment) - (len(all_lines[-1]) - end_offset)]

            anchors = None
            show_carets = False
            with contextlib.suppress(Exception):
                anchors = traceback._extract_caret_anchors_from_line_segment(segment)
            show_carets = self._should_show_carets(start_offset, end_offset, all_lines, anchors)

            result = []
            significant_lines = {0, len(all_lines) - 1}

            anchors_left_end_offset = 0
            anchors_right_start_offset = 0
            primary_char = "^"
            secondary_char = "^"
            if anchors:
                anchors_left_end_offset = anchors.left_end_offset
                anchors_right_start_offset = anchors.right_start_offset
                if anchors.left_end_lineno == 0:
                    anchors_left_end_offset += start_offset
                if anchors.right_start_lineno == 0:
                    anchors_right_start_offset += start_offset

                anchors_left_end_offset = traceback._display_width(
                    all_lines[anchors.left_end_lineno], offset=anchors_left_end_offset
                )
                anchors_right_start_offset = traceback._display_width(
                    all_lines[anchors.right_start_lineno], offset=anchors_right_start_offset
                )

                primary_char = anchors.primary_char
                secondary_char = anchors.secondary_char
                significant_lines.update(
                    range(anchors.left_end_lineno - 1, anchors.left_end_lineno + 2)
                )
                significant_lines.update(
                    range(anchors.right_start_lineno - 1, anchors.right_start_lineno + 2)
                )

            significant_lines.discard(-1)
            significant_lines.discard(len(all_lines))

            def output_line(lineno):
                result.append(all_lines[lineno] + "\n")
                if not show_carets:
                    return
                num_spaces = len(all_lines[lineno]) - len(all_lines[lineno].lstrip())
                num_carets = (
                    dp_end_offset if lineno == len(all_lines) - 1
                    else traceback._display_width(all_lines[lineno])
                )
                carets = []
                for col in range(num_carets):
                    if col < num_spaces or (lineno == 0 and col < dp_start_offset):
                        carets.append(" ")
                    elif anchors and (
                        lineno > anchors.left_end_lineno or
                        (lineno == anchors.left_end_lineno and col >= anchors_left_end_offset)
                    ) and (
                        lineno < anchors.right_start_lineno or
                        (lineno == anchors.right_start_lineno and col < anchors_right_start_offset)
                    ):
                        carets.append(secondary_char)
                    else:
                        carets.append(primary_char)
                result.append("".join(carets) + "\n")

            sig_lines_list = sorted(significant_lines)
            for i, lineno in enumerate(sig_lines_list):
                if i:
                    linediff = lineno - sig_lines_list[i - 1]
                    if linediff == 2:
                        output_line(lineno - 1)
                    elif linediff > 2:
                        result.append(f"...<{linediff - 1} lines>...\n")
                output_line(lineno)

            row.append(textwrap.indent(textwrap.dedent("".join(result)), "    ", lambda line: True))

    if frame_summary.locals:
        for name, value in sorted(frame_summary.locals.items()):
            row.append(f"    {name} = {value}\n")
    return "".join(row)


def _candidate_stack_format_no_color(self, **kwargs):
    if kwargs.get("colorize", False):
        return _ORIGINAL_STACK_FORMAT(self, **kwargs)

    result = []
    append = result.append
    last_file = None
    last_line = None
    last_name = None
    count = 0
    format_frame_summary = self.format_frame_summary
    recursive_cutoff = traceback._RECURSIVE_CUTOFF

    for frame_summary in self:
        formatted_frame = format_frame_summary(frame_summary)
        if formatted_frame is None:
            continue
        if (
            last_file is None or last_file != frame_summary.filename or
            last_line is None or last_line != frame_summary.lineno or
            last_name is None or last_name != frame_summary.name
        ):
            if count > recursive_cutoff:
                repeat = count - recursive_cutoff
                append(
                    f'  [Previous line repeated {repeat} more time{"s" if repeat > 1 else ""}]\n'
                )
            last_file = frame_summary.filename
            last_line = frame_summary.lineno
            last_name = frame_summary.name
            count = 0
        count += 1
        if count > recursive_cutoff:
            continue
        append(formatted_frame)

    if count > recursive_cutoff:
        repeat = count - recursive_cutoff
        append(
            f'  [Previous line repeated {repeat} more time{"s" if repeat > 1 else ""}]\n'
        )
    return result


class Variant:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        if self.name == "runtime":
            return
        if self.name == "frame_no_color":
            traceback.StackSummary.format_frame_summary = _candidate_format_frame_summary_no_color
            return
        if self.name == "stack_no_color":
            traceback.StackSummary.format = _candidate_stack_format_no_color
            return
        if self.name == "frame_stack_no_color":
            traceback.StackSummary.format_frame_summary = _candidate_format_frame_summary_no_color
            traceback.StackSummary.format = _candidate_stack_format_no_color
            return
        raise ValueError(f"unknown variant: {self.name}")

    def __exit__(self, exc_type, exc, tb):
        traceback.StackSummary.format_frame_summary = _ORIGINAL_FORMAT_FRAME_SUMMARY
        traceback.StackSummary.format = _ORIGINAL_STACK_FORMAT


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
    parser.add_argument(
        "--variant",
        choices=("runtime", "frame_no_color", "stack_no_color", "frame_stack_no_color"),
        default="runtime",
    )
    parser.add_argument("--loops-frame", type=int, default=20_000)
    parser.add_argument("--loops-stack", type=int, default=8_000)
    parser.add_argument("--loops-te", type=int, default=6_000)
    parser.add_argument("--loops-format-exc", type=int, default=4_000)
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        results = {
            "variant": ns.variant,
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

    print(f"[variant={ns.variant}]")
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
