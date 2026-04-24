#!/usr/bin/env python3
"""Guardrails for pure-Python pickle load/read fast-path candidates."""

from __future__ import annotations

import io
import pathlib
import pickle
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


OBJECTS = [
    list(range(50)),
    {"a": 1, "b": [1, 2, 3], "c": ("x", "y")},
    [f"name-{i}" for i in range(200)],
    bytearray(b"x" * 4096),
]

PAYLOADS = [pickle._dumps(obj, protocol=5) for obj in OBJECTS]
STREAM = b"".join(PAYLOADS)


def capture(fn):
    try:
        result = fn()
    except BaseException as exc:  # noqa: BLE001
        return (type(exc), exc.args)
    return ("ok", result)


def load_stream():
    u = pickle._Unpickler(io.BytesIO(STREAM))
    return [u.load() for _ in range(len(PAYLOADS))]


def main() -> None:
    baseline = {
        "loads": [capture(lambda payload=payload: pickle._loads(payload)) for payload in PAYLOADS],
        "stream": capture(load_stream),
        "truncated": capture(lambda: pickle._loads(PAYLOADS[0][:-1])),
    }

    install_candidate()
    try:
        candidate = {
            "loads": [capture(lambda payload=payload: pickle._loads(payload)) for payload in PAYLOADS],
            "stream": capture(load_stream),
            "truncated": capture(lambda: pickle._loads(PAYLOADS[0][:-1])),
        }
    finally:
        restore_original()

    assert baseline == candidate, (baseline, candidate)
    print("pickle pure load/read guardrails: ok")


if __name__ == "__main__":
    main()
