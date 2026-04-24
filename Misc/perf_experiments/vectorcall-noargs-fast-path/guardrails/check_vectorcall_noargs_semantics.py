from __future__ import annotations


def plain_noargs() -> int:
    return 1


def closure_noargs_factory():
    x = 5

    def inner() -> int:
        return x

    return inner


class NoArgMethod:
    def __init__(self, value: int) -> None:
        self.value = value

    def method(self) -> int:
        return self.value


def defaults_not_noargs(x: int = 7, y: int = 9) -> int:
    return x + y


def kwonly_required(*, flag: bool) -> bool:
    return flag


def main() -> int:
    assert plain_noargs() == 1
    assert closure_noargs_factory()() == 5
    assert NoArgMethod(11).method() == 11
    assert defaults_not_noargs() == 16
    assert defaults_not_noargs(y=4) == 11

    try:
        kwonly_required()
    except TypeError as exc:
        assert "required keyword-only argument" in str(exc)
    else:
        raise AssertionError("kwonly_required() should fail without flag")

    print("vectorcall noargs semantics: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
