#!/usr/bin/env python3
"""Guardrails for pickletools._genops() fast-path candidates."""

from __future__ import annotations

import io
import pathlib
import pickle
import pickletools
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


class NoTellReader:
    def __init__(self, data: bytes) -> None:
        self._bio = io.BytesIO(data)

    def read(self, n: int = -1) -> bytes:
        return self._bio.read(n)


PAYLOADS = [
    pickle.dumps(list(range(100)), protocol=5),
    pickle.dumps(tuple(range(256)), protocol=5),
    pickle.dumps({"items": [{"id": i, "name": f"n{i}"} for i in range(60)]}, protocol=5),
    pickle.dumps((["x" * 64] * 200, {"k": list(range(50))}), protocol=4),
    pickle.dumps([("x", i) for i in range(50)], protocol=2),
]


def _capture_genops(payload: bytes, *, yield_end_pos: bool, use_no_tell: bool):
    if use_no_tell:
        source = NoTellReader(payload)
    else:
        source = payload
    return list(pickletools._genops(source, yield_end_pos=yield_end_pos))


def _capture_public_genops(payload: bytes):
    return list(pickletools.genops(payload))


def _capture_optimize(payload: bytes):
    return pickletools.optimize(payload)


def _capture_dis(payload: bytes):
    out = io.StringIO()
    pickletools.dis(payload, out=out)
    return out.getvalue()


def main() -> None:
    baseline = {
        "genops": [_capture_genops(p, yield_end_pos=False, use_no_tell=False) for p in PAYLOADS],
        "genops_end": [_capture_genops(p, yield_end_pos=True, use_no_tell=False) for p in PAYLOADS],
        "genops_no_tell": [_capture_genops(p, yield_end_pos=False, use_no_tell=True) for p in PAYLOADS],
        "genops_end_no_tell": [_capture_genops(p, yield_end_pos=True, use_no_tell=True) for p in PAYLOADS],
        "public_genops": [_capture_public_genops(p) for p in PAYLOADS],
        "optimize": [_capture_optimize(p) for p in PAYLOADS],
        "dis": [_capture_dis(p) for p in PAYLOADS],
    }

    install_candidate("byte_table")
    try:
        candidate = {
            "genops": [_capture_genops(p, yield_end_pos=False, use_no_tell=False) for p in PAYLOADS],
            "genops_end": [_capture_genops(p, yield_end_pos=True, use_no_tell=False) for p in PAYLOADS],
            "genops_no_tell": [_capture_genops(p, yield_end_pos=False, use_no_tell=True) for p in PAYLOADS],
            "genops_end_no_tell": [_capture_genops(p, yield_end_pos=True, use_no_tell=True) for p in PAYLOADS],
            "public_genops": [_capture_public_genops(p) for p in PAYLOADS],
            "optimize": [_capture_optimize(p) for p in PAYLOADS],
            "dis": [_capture_dis(p) for p in PAYLOADS],
        }
    finally:
        restore_original()

    assert baseline == candidate
    print("pickletools genops guardrails: ok")


if __name__ == "__main__":
    main()
