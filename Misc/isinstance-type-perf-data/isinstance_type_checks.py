#!/usr/bin/env python3
from __future__ import annotations

import abc
from typing import Protocol, runtime_checkable


class RegisteredABC(metaclass=abc.ABCMeta):
    pass


RegisteredABC.register(dict)


class PropertyProxy:
    @property
    def __class__(self):
        return dict


class GetattributeProxy:
    def __getattribute__(self, name):
        if name == "__class__":
            return dict
        return object.__getattribute__(self, name)


@runtime_checkable
class SupportsClose(Protocol):
    def close(self) -> None: ...


@runtime_checkable
class HasX(Protocol):
    x: int


class Closable:
    def close(self) -> None:
        return None


class MaybeX:
    def __init__(self, has_x: bool) -> None:
        if has_x:
            self.x = 1


def main() -> None:
    assert isinstance({}, RegisteredABC)
    assert isinstance(PropertyProxy(), RegisteredABC)
    assert isinstance(GetattributeProxy(), RegisteredABC)

    assert isinstance(Closable(), SupportsClose)
    assert isinstance(MaybeX(True), HasX)
    assert not isinstance(MaybeX(False), HasX)

    class Base:
        pass

    class Child(Base):
        pass

    assert isinstance(Child(), Base)
    assert not isinstance(Base(), Child)

    print("semantic checks passed")


if __name__ == "__main__":
    main()
