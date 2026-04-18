from __future__ import annotations

from functools import cached_property


def assert_equal(left, right, message: str) -> None:
    if left != right:
        raise AssertionError(f"{message}: {left!r} != {right!r}")


def check_property_beats_instance_dict() -> None:
    class Sample:
        def __init__(self) -> None:
            self.__dict__["value"] = "shadowed"

        @property
        def value(self) -> str:
            return "property"

    assert_equal(getattr(Sample(), "value"), "property", "property precedence changed")


def check_instance_dict_beats_non_data_descriptor() -> None:
    class Sample:
        def method(self) -> str:
            return "descriptor"

    sample = Sample()
    sample.method = "instance"
    assert_equal(getattr(sample, "method"), "instance", "instance dict lost to non-data descriptor")


def check_custom_getattribute() -> None:
    class Sample:
        def __getattribute__(self, name: str):
            if name == "magic":
                return 99
            return super().__getattribute__(name)

    assert_equal(getattr(Sample(), "magic"), 99, "__getattribute__ fast path changed")


def check_getattr_fallback() -> None:
    class Sample:
        def __getattr__(self, name: str):
            if name == "fallback":
                return "ok"
            raise AttributeError(name)

    assert_equal(getattr(Sample(), "fallback"), "ok", "__getattr__ fallback changed")


def check_slots_descriptor() -> None:
    class Sample:
        __slots__ = ("count",)

        def __init__(self) -> None:
            self.count = 7

    assert_equal(getattr(Sample(), "count"), 7, "slot member descriptor changed")


def check_cached_property() -> None:
    class Sample:
        def __init__(self) -> None:
            self.calls = 0

        @cached_property
        def result(self) -> int:
            self.calls += 1
            return 42

    sample = Sample()
    assert_equal(getattr(sample, "result"), 42, "cached_property first access changed")
    assert_equal(getattr(sample, "result"), 42, "cached_property cached access changed")
    assert_equal(sample.calls, 1, "cached_property recomputed unexpectedly")


def main() -> None:
    check_property_beats_instance_dict()
    check_instance_dict_beats_non_data_descriptor()
    check_custom_getattribute()
    check_getattr_fallback()
    check_slots_descriptor()
    check_cached_property()
    print("semantic checks passed")


if __name__ == "__main__":
    main()
