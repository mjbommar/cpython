#!/usr/bin/env python3
"""Guardrail for tokenize.detect_encoding fast-path ideas."""

from __future__ import annotations

import importlib._bootstrap_external as bootstrap_external
import pathlib
import tempfile
import tokenize


def check_detect_encoding() -> None:
    encoding, lines = tokenize.detect_encoding(iter([b'"""doc"""\n']).__next__)
    assert encoding == "utf-8"
    assert lines == [b'"""doc"""\n']

    encoding, lines = tokenize.detect_encoding(iter([tokenize.BOM_UTF8 + b'"""doc"""\n']).__next__)
    assert encoding == "utf-8-sig"
    assert lines == [b'"""doc"""\n']

    encoding, lines = tokenize.detect_encoding(iter([b"# coding: latin-1\n"]).__next__)
    assert encoding == "iso-8859-1"
    assert lines == [b"# coding: latin-1\n"]

    encoding, lines = tokenize.detect_encoding(
        iter([b"#!/usr/bin/env python3\n", b"# coding: latin-1\n"]).__next__
    )
    assert encoding == "iso-8859-1"
    assert lines == [b"#!/usr/bin/env python3\n", b"# coding: latin-1\n"]

    try:
        tokenize.detect_encoding(iter([b"# coding: definitely-not-real\n"]).__next__)
    except SyntaxError:
        pass
    else:
        raise AssertionError("invalid cookie unexpectedly succeeded")

    try:
        tokenize.detect_encoding(iter([b"\xff\n"]).__next__)
    except SyntaxError:
        pass
    else:
        raise AssertionError("invalid utf-8 unexpectedly succeeded")

    try:
        tokenize.detect_encoding(iter([b"x = 1\0\n"]).__next__)
    except SyntaxError:
        pass
    else:
        raise AssertionError("null byte unexpectedly succeeded")


def check_open_and_decode_source() -> None:
    with tempfile.TemporaryDirectory(prefix="guard-tokenize-") as tmp:
        tmpdir = pathlib.Path(tmp)
        default_path = tmpdir / "default.py"
        cookie_path = tmpdir / "cookie.py"
        default_path.write_bytes('"""caf\xe9"""\nimport os\n'.encode("utf-8"))
        cookie_path.write_bytes(b"# coding: latin-1\ns = 'caf\xe9'\n")

        with tokenize.open(default_path) as f:
            assert f.readline() == '"""caf\xe9"""\n'
            assert f.readline() == "import os\n"

        with tokenize.open(cookie_path) as f:
            assert f.readline() == "# coding: latin-1\n"
            assert f.readline() == "s = 'caf\xe9'\n"

        assert bootstrap_external.decode_source(default_path.read_bytes()).startswith('"""caf\xe9"""')
        assert "caf\xe9" in bootstrap_external.decode_source(cookie_path.read_bytes())


def main() -> None:
    check_detect_encoding()
    check_open_and_decode_source()
    print("tokenize detect_encoding semantics: ok")


if __name__ == "__main__":
    main()
