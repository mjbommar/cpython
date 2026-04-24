#!/usr/bin/env python3
"""Guardrails for pure-Python pickle save-side batch fast-path candidates."""

from __future__ import annotations

import io
import pathlib
import pickle
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


class MyList(list):
    pass


class IntPersistentPickler(pickle._Pickler):
    def persistent_id(self, obj):
        if type(obj) is int and obj % 17 == 0:
            return f"int:{obj}"
        return None


OBJECTS = [
    list(range(100)),
    [7] * 128,
    [True, False] * 100,
    [0, "x", 1.5, None, True] * 20,
    [[i] * 10 for i in range(50)],
    [{"id": i, "name": f"n{i}", "v": i * 2} for i in range(50)],
    MyList(range(30)),
]


def dump_with_pickler(obj, pickler_cls=pickle._Pickler):
    bio = io.BytesIO()
    pickler_cls(bio, protocol=5).dump(obj)
    return bio.getvalue()


def capture_dumps(pickler_cls):
    return [dump_with_pickler(obj, pickler_cls=pickler_cls) for obj in OBJECTS]


def main() -> None:
    baseline = {
        "dumps": capture_dumps(pickle._Pickler),
        "persistent": capture_dumps(IntPersistentPickler),
    }
    baseline_roundtrip = [pickle.loads(data) for data in baseline["dumps"]]

    for variant in ("exact_int_lists", "exact_int_lists_min8"):
        install_candidate(variant)
        try:
            candidate = {
                "dumps": capture_dumps(pickle._Pickler),
                "persistent": capture_dumps(IntPersistentPickler),
            }
        finally:
            restore_original()

        assert baseline == candidate, variant
        roundtrip = [pickle.loads(data) for data in candidate["dumps"]]
        assert baseline_roundtrip == roundtrip, variant

    print("pickle pure save batch guardrails: ok")


if __name__ == "__main__":
    main()
