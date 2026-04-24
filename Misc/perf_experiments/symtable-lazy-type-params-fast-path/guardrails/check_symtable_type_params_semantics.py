from __future__ import annotations

import symtable


def find_child(table, name: str):
    for child in table.get_children():
        if child.get_name() == name:
            return child
    raise AssertionError(f"missing child {name!r}")


def main() -> int:
    nested = symtable.symtable(
        "def outer(x):\n"
        "    y = x + 1\n"
        "    def inner(z):\n"
        "        return y + z\n"
        "    return inner\n",
        "<nested>",
        "exec",
    )
    outer = find_child(nested, "outer")
    inner = find_child(outer, "inner")
    assert outer.lookup("x").is_parameter()
    assert outer.lookup("y").is_local()
    assert inner.lookup("z").is_parameter()
    assert inner.lookup("y").is_free()

    generic = symtable.symtable(
        "def f[T](x: T, y: T) -> T:\n"
        "    return x if x else y\n",
        "<generic>",
        "exec",
    )
    type_params = find_child(generic, "f")
    assert type_params.lookup("T").is_type_parameter()
    f = find_child(type_params, "f")
    assert f.lookup("x").is_parameter()
    assert f.lookup("y").is_parameter()

    generic_class = symtable.symtable(
        "class Box[T]:\n"
        "    def __init__(self, value: T):\n"
        "        self.value = value\n"
        "    def get(self) -> T:\n"
        "        return self.value\n",
        "<generic-class>",
        "exec",
    )
    type_params = find_child(generic_class, "Box")
    assert type_params.lookup("T").is_type_parameter()
    box = find_child(type_params, "Box")
    assert box.lookup("__init__").is_namespace()

    try:
        symtable.symtable(
            "def outer[T]():\n"
            "    def inner():\n"
            "        nonlocal T\n",
            "<bad-nonlocal>",
            "exec",
        )
    except SyntaxError as exc:
        assert "type parameter" in str(exc)
    else:
        raise AssertionError("expected SyntaxError for nonlocal type parameter")

    print("symtable type_params semantics: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
