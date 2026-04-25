#!/usr/bin/env python3
"""Guardrail for tarfile stream read fast-path ideas."""

from __future__ import annotations

import io
import tarfile


PAYLOADS = {
    "alpha.txt": (b"alpha\n" * 64),
    "beta.bin": bytes(range(64)) * 32,
    "nested/gamma.txt": (b"gamma-data-" * 200),
}


def build_archive(mode: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for name, data in PAYLOADS.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


ARCHIVES = {
    "gz": build_archive("w|gz"),
    "bz2": build_archive("w|bz2"),
    "xz": build_archive("w|xz"),
}


def read_archive(mode: str, payload: bytes, *, chunked: bool) -> tuple[list[str], dict[str, bytes]]:
    names = []
    contents = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode=mode) as tf:
        for member in tf:
            names.append(member.name)
            if not member.isreg():
                continue
            with tf.extractfile(member) as f:
                if chunked:
                    parts = []
                    while True:
                        block = f.read(257)
                        if not block:
                            break
                        parts.append(block)
                    contents[member.name] = b"".join(parts)
                else:
                    contents[member.name] = f.read()
    return names, contents


def check_good_modes() -> None:
    expected_names = list(PAYLOADS)
    for comptype, payload in ARCHIVES.items():
        names, contents = read_archive(f"r|{comptype}", payload, chunked=True)
        assert names == expected_names
        assert contents == PAYLOADS

        names, contents = read_archive(f"r|{comptype}", payload, chunked=False)
        assert names == expected_names
        assert contents == PAYLOADS

    names, contents = read_archive("r|*", ARCHIVES["bz2"], chunked=True)
    assert names == expected_names
    assert contents == PAYLOADS


def check_internal_stream_reads() -> None:
    for comptype, payload in ARCHIVES.items():
        stream = tarfile._Stream(
            "guardrail.tar",
            "r",
            comptype,
            io.BytesIO(payload),
            tarfile.RECORDSIZE,
            None,
            None,
        )
        try:
            chunks = []
            while True:
                block = stream._read(257)
                if not block:
                    break
                chunks.append(block)
            data = b"".join(chunks)
            assert len(data) >= sum(len(v) for v in PAYLOADS.values())
        finally:
            stream.close()


def check_bad_data() -> None:
    for comptype in ARCHIVES:
        broken = b"not-a-valid-compressed-tar-stream"
        try:
            with tarfile.open(fileobj=io.BytesIO(broken), mode=f"r|{comptype}") as tf:
                for member in tf:
                    if member.isreg():
                        with tf.extractfile(member) as f:
                            while f.read(257):
                                pass
        except (EOFError, tarfile.ReadError, tarfile.CompressionError, OSError):
            continue
        raise AssertionError(f"truncated {comptype} stream unexpectedly succeeded")


def main() -> None:
    check_good_modes()
    check_internal_stream_reads()
    check_bad_data()
    print("tarfile stream semantics: ok")


if __name__ == "__main__":
    main()
