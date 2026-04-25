from __future__ import annotations

import tarfile


ORIGINAL_READ = tarfile._Stream._read
ORIGINAL_TAR_READ = tarfile._Stream._Stream__read


def candidate_common_case_split(self, size):
    if self.comptype == "tar":
        return ORIGINAL_TAR_READ(self, size)

    dbuf = self.dbuf
    if len(dbuf) >= size:
        self.dbuf = dbuf[size:]
        return dbuf[:size]

    if self.buf:
        raw = self.buf
        self.buf = b""
    else:
        raw = self.fileobj.read(self.bufsize)
        if not raw:
            self.dbuf = b""
            return dbuf

    try:
        chunk = self.cmp.decompress(raw)
    except self.exception as e:
        raise tarfile.ReadError("invalid compressed data") from e

    data = dbuf + chunk
    if len(data) >= size:
        self.dbuf = data[size:]
        return data[:size]

    parts = [data]
    total = len(data)
    while total < size:
        if self.buf:
            raw = self.buf
            self.buf = b""
        else:
            raw = self.fileobj.read(self.bufsize)
            if not raw:
                break
        try:
            chunk = self.cmp.decompress(raw)
        except self.exception as e:
            raise tarfile.ReadError("invalid compressed data") from e
        parts.append(chunk)
        total += len(chunk)

    data = b"".join(parts)
    self.dbuf = data[size:]
    return data[:size]


def candidate_common_case_split_direct(self, size):
    if self.comptype == "tar":
        return ORIGINAL_TAR_READ(self, size)

    dbuf = self.dbuf
    if len(dbuf) >= size:
        self.dbuf = dbuf[size:]
        return dbuf[:size]

    if self.buf:
        raw = self.buf
        self.buf = b""
    else:
        raw = self.fileobj.read(self.bufsize)
        if not raw:
            self.dbuf = b""
            return dbuf

    try:
        chunk = self.cmp.decompress(raw)
    except self.exception as e:
        raise tarfile.ReadError("invalid compressed data") from e

    if not dbuf and len(chunk) >= size:
        self.dbuf = chunk[size:]
        return chunk[:size]

    data = dbuf + chunk
    if len(data) >= size:
        self.dbuf = data[size:]
        return data[:size]

    parts = [data]
    total = len(data)
    while total < size:
        if self.buf:
            raw = self.buf
            self.buf = b""
        else:
            raw = self.fileobj.read(self.bufsize)
            if not raw:
                break
        try:
            chunk = self.cmp.decompress(raw)
        except self.exception as e:
            raise tarfile.ReadError("invalid compressed data") from e
        parts.append(chunk)
        total += len(chunk)

    data = b"".join(parts)
    self.dbuf = data[size:]
    return data[:size]


def install_candidate(variant: str) -> None:
    if variant == "common_case_split":
        tarfile._Stream._read = candidate_common_case_split
        return
    if variant == "common_case_split_direct":
        tarfile._Stream._read = candidate_common_case_split_direct
        return
    raise ValueError(f"unknown variant: {variant}")


def restore_original() -> None:
    tarfile._Stream._read = ORIGINAL_READ
