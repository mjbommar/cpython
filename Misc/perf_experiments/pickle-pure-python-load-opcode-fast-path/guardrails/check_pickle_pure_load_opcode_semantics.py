#!/usr/bin/env python3
"""Guardrail for pure-Python pickle load opcode fast-path candidates."""

from __future__ import annotations

import io
import pathlib
import pickle
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


OBJECTS = [
    [f"name-{i}" for i in range(40)],
    list(range(80)),
    [(i, i + 1, i + 2) for i in range(25)],
    {"outer": [{"k": i, "triple": (i, i + 1, i + 2)} for i in range(12)]},
    [{"k": i, "ok": True, "s": f"v-{i}"} for i in range(30)],
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

    install_candidate("inline_hot_opcodes")
    try:
        candidate = {
            "loads": [capture(lambda payload=payload: pickle._loads(payload)) for payload in PAYLOADS],
            "stream": capture(load_stream),
            "truncated": capture(lambda: pickle._loads(PAYLOADS[0][:-1])),
        }
    finally:
        restore_original()

    assert baseline == candidate, (baseline, candidate)
    print("pickle pure load opcode guardrails: ok")


if __name__ == "__main__":
    main()
