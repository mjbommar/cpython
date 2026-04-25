#!/usr/bin/env python3
from __future__ import annotations

import bz2
import io
import lzma
import pathlib

from compression._common import _streams
from _bz2 import BZ2Decompressor
from _lzma import LZMADecompressor, LZMAError


ROOT = pathlib.Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT))

from helpers import install_candidate, restore_original  # noqa: E402


DATA = (bytes(range(64)) * 512) + (b"line\n" * 4096)
DATA_A = DATA[: len(DATA) // 2]
DATA_B = DATA[len(DATA) // 2 :]


def _read_chunks(reader, size: int) -> bytes:
    parts = []
    while True:
        chunk = reader.read(size)
        if not chunk:
            break
        parts.append(chunk)
    return b"".join(parts)


def _check_raw(factory, trailing_error, compressed: bytes, expected: bytes) -> None:
    reader = _streams.DecompressReader(io.BytesIO(compressed), factory, trailing_error=trailing_error)
    assert reader.read(0) == b""
    prefix = reader.read(123)
    assert prefix == expected[:123]
    assert reader.tell() == 123
    assert _read_chunks(reader, 4096) == expected[123:]
    assert reader.read(1) == b""
    assert reader.tell() == len(expected)

    seek_reader = _streams.DecompressReader(io.BytesIO(compressed), factory, trailing_error=trailing_error)
    assert seek_reader.seek(777) == 777
    assert seek_reader.tell() == 777
    assert seek_reader.read(321) == expected[777:1098]

    trailing_reader = _streams.DecompressReader(io.BytesIO(compressed + b"notastream"), factory, trailing_error=trailing_error)
    assert trailing_reader.read() == expected

    broken_reader = _streams.DecompressReader(io.BytesIO(compressed[:-5]), factory, trailing_error=trailing_error)
    try:
        broken_reader.read(len(expected) + 1)
    except EOFError:
        pass
    else:
        raise AssertionError("truncated stream should still raise EOFError")


def _check_file(file_factory, compressed: bytes, expected: bytes) -> None:
    with file_factory(io.BytesIO(compressed), "rb") as fp:
        assert fp.read(0) == b""
        assert fp.read(257) == expected[:257]
        assert fp.read() == expected[257:]

    with file_factory(io.BytesIO(compressed), "rb") as fp:
        assert fp.seek(999) == 999
        assert fp.read(111) == expected[999:1110]


def main() -> int:
    install_candidate("common_case_split")
    try:
        bz2_single = bz2.compress(DATA, compresslevel=9)
        lzma_single = lzma.compress(DATA)
        bz2_multi = bz2.compress(DATA_A, compresslevel=9) + bz2.compress(DATA_B, compresslevel=9)
        lzma_multi = lzma.compress(DATA_A) + lzma.compress(DATA_B)

        _check_raw(BZ2Decompressor, OSError, bz2_single, DATA)
        _check_raw(BZ2Decompressor, OSError, bz2_multi, DATA_A + DATA_B)
        _check_raw(LZMADecompressor, LZMAError, lzma_single, DATA)
        _check_raw(LZMADecompressor, LZMAError, lzma_multi, DATA_A + DATA_B)

        _check_file(bz2.BZ2File, bz2_single, DATA)
        _check_file(lzma.LZMAFile, lzma_single, DATA)
    finally:
        restore_original()

    print("decompress reader semantics: ok")
    return 0
