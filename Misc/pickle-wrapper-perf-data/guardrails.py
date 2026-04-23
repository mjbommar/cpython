#!/usr/bin/env python3

from __future__ import annotations

import io
import pickle


PERSISTENT_LOAD_ERROR = (
    "A load persistent id instruction was encountered, "
    "but no persistent_load function was specified."
)


class PersistentIdPickler(pickle.Pickler):
    def persistent_id(self, obj):
        if obj == "persist-me":
            return "token-1"
        return None


def build_persistent_payload() -> bytes:
    bio = io.BytesIO()
    pickler = PersistentIdPickler(bio, protocol=2)
    pickler.dump(["persist-me", "plain"])
    return bio.getvalue()


def test_exact_pickler_instance_override() -> None:
    seen = []
    bio = io.BytesIO()
    pickler = pickle.Pickler(bio, protocol=2)
    pickler.persistent_id = lambda obj: seen.append(obj) or ("tok" if obj == "persist-me" else None)
    pickler.dump(["persist-me", "plain"])
    assert seen


def test_exact_unpickler_default_error() -> None:
    payload = build_persistent_payload()
    try:
        pickle.Unpickler(io.BytesIO(payload)).load()
    except pickle.UnpicklingError as exc:
        assert str(exc) == PERSISTENT_LOAD_ERROR
    else:
        raise AssertionError("expected UnpicklingError")


def test_exact_unpickler_instance_override() -> None:
    payload = build_persistent_payload()
    unpickler = pickle.Unpickler(io.BytesIO(payload))
    unpickler.persistent_load = lambda pid: f"loaded:{pid}"
    value = unpickler.load()
    assert value == ["loaded:token-1", "plain"]


def test_subclass_unpickler_override() -> None:
    payload = build_persistent_payload()

    class CustomUnpickler(pickle.Unpickler):
        def persistent_load(self, pid):
            return {"pid": pid}

    value = CustomUnpickler(io.BytesIO(payload)).load()
    assert value == [{"pid": "token-1"}, "plain"]


def main() -> None:
    test_exact_pickler_instance_override()
    test_exact_unpickler_default_error()
    test_exact_unpickler_instance_override()
    test_subclass_unpickler_override()
    print("pickle wrapper guardrails: ok")


if __name__ == "__main__":
    main()
