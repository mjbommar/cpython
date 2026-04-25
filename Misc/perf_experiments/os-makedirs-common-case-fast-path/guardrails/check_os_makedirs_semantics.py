#!/usr/bin/env python3
"""Guardrails for os.makedirs common-case fast-path ideas."""

from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import candidate_mkdir_first


def run_and_capture(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001
        return ("exc", type(exc), exc.args)
    return ("ok", None, None)


def assert_same(result_a, result_b, context):
    if result_a != result_b:
        raise AssertionError(f"{context}: result mismatch: {result_a!r} != {result_b!r}")


def assert_tree(path, expected, context):
    actual = sorted(os.listdir(path))
    if actual != sorted(expected):
        raise AssertionError(f"{context}: tree mismatch: {actual!r} != {expected!r}")


def case_simple_leaf(func, root):
    parent = os.path.join(root, "parent")
    os.mkdir(parent)
    leaf = os.path.join(parent, "leaf")
    result = run_and_capture(func, leaf)
    state = (os.path.isdir(parent), os.path.isdir(leaf))
    return result, state


def case_nested(func, root):
    path = os.path.join(root, "a", "b", "c")
    result = run_and_capture(func, path)
    state = (
        os.path.isdir(os.path.join(root, "a")),
        os.path.isdir(os.path.join(root, "a", "b")),
        os.path.isdir(path),
    )
    return result, state


def case_trailing_dot(func, root):
    path = os.path.join(root, "dot", os.curdir)
    result = run_and_capture(func, path)
    state = os.path.isdir(os.path.join(root, "dot"))
    return result, state


def case_bytes(func, root):
    parent = os.path.join(root, "bytes-parent")
    os.mkdir(parent)
    leaf = os.fsencode(os.path.join(parent, "leaf"))
    result = run_and_capture(func, leaf)
    state = os.path.isdir(os.path.join(parent, "leaf"))
    return result, state


def case_exist_ok_existing(func, root):
    path = os.path.join(root, "existing")
    os.mkdir(path)
    result = run_and_capture(func, path, exist_ok=True)
    state = os.path.isdir(path)
    return result, state


def case_exists_error(func, root):
    path = os.path.join(root, "existing")
    os.mkdir(path)
    result = run_and_capture(func, path)
    state = os.path.isdir(path)
    return result, state


def case_parent_is_file(func, root):
    parent = os.path.join(root, "file-parent")
    with open(parent, "wb") as f:
        f.write(b"x")
    path = os.path.join(parent, "leaf")
    result = run_and_capture(func, path)
    state = os.path.isfile(parent)
    return result, state


def main() -> None:
    baseline = os.makedirs
    cases = [
        ("simple_leaf", case_simple_leaf),
        ("nested", case_nested),
        ("trailing_dot", case_trailing_dot),
        ("bytes_leaf", case_bytes),
        ("exist_ok_existing", case_exist_ok_existing),
        ("exists_error", case_exists_error),
        ("parent_is_file", case_parent_is_file),
    ]

    for name, case in cases:
        root_a = tempfile.mkdtemp(prefix=f"os-makedirs-base-{name}-")
        root_b = tempfile.mkdtemp(prefix=f"os-makedirs-cand-{name}-")
        try:
            baseline_result = case(baseline, root_a)
            candidate_result = case(candidate_mkdir_first, root_b)
            assert_same(baseline_result, candidate_result, name)
        finally:
            shutil.rmtree(root_a, ignore_errors=True)
            shutil.rmtree(root_b, ignore_errors=True)

    print("os makedirs semantics: ok")


if __name__ == "__main__":
    main()
