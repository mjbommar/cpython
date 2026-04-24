#!/usr/bin/env python3
"""Guardrails for pure-Python pickle tuple fast-path experiments."""

from __future__ import annotations

import io
import pathlib
import pickle
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


def dump_bytes(obj):
    bio = io.BytesIO()
    pickle._Pickler(bio, protocol=5).dump(obj)
    return bio.getvalue()


def assert_same_bytes(obj):
    baseline = dump_bytes(obj)
    install_candidate("exact_int_tuples")
    try:
        candidate = dump_bytes(obj)
    finally:
        restore_original()
    if baseline != candidate:
        raise AssertionError(f"bytes differ for {obj!r}")


def assert_roundtrip(obj):
    install_candidate("exact_int_tuples")
    try:
        data = dump_bytes(obj)
    finally:
        restore_original()
    restored = pickle.loads(data)
    if restored != obj:
        raise AssertionError(f"roundtrip differs for {obj!r}")


class IntPersistentPickler(pickle._Pickler):
    def persistent_id(self, obj):
        if type(obj) is int and obj == 7:
            return "seven"
        return None


def assert_subclass_fallback():
    payload = (7, 8, 9)
    install_candidate("exact_int_tuples")
    try:
        bio = io.BytesIO()
        IntPersistentPickler(bio, protocol=5).dump(payload)
        data = bio.getvalue()
    finally:
        restore_original()
    if b"seven" not in data:
        raise AssertionError("subclass persistent_id fallback was bypassed")


def main() -> int:
    fixtures = [
        (),
        (1,),
        (1, 2),
        (1, 2, 3),
        tuple(range(32)),
        tuple(range(1024)),
        tuple(f"item_{i}" for i in range(32)),
        ((1, 2), (3, 4), (5, 6)),
        (0, "x", 1.5, None, True),
        tuple({"id": i, "name": f"n{i}"} for i in range(10)),
    ]

    for obj in fixtures:
        assert_same_bytes(obj)
        assert_roundtrip(obj)

    assert_subclass_fallback()
    print("pickle pure tuple guardrails: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
