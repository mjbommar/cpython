from __future__ import annotations

from compression._common import _streams


ORIGINAL_READ = _streams.DecompressReader.read


def candidate_common_case_split(self, size=-1):
    if size < 0:
        return self.readall()

    if not size or self._eof:
        return b""

    decompressor = self._decompressor
    if not decompressor.eof:
        if decompressor.needs_input:
            rawblock = self._fp.read(_streams.BUFFER_SIZE)
            if not rawblock:
                raise EOFError("Compressed file ended before the end-of-stream marker was reached")
        else:
            rawblock = b""
        data = decompressor.decompress(rawblock, size)
        if data:
            self._pos += len(data)
            return data

    data = None
    while True:
        if decompressor.eof:
            rawblock = decompressor.unused_data or self._fp.read(_streams.BUFFER_SIZE)
            if not rawblock:
                break
            decompressor = self._decomp_factory(**self._decomp_args)
            self._decompressor = decompressor
            try:
                data = decompressor.decompress(rawblock, size)
            except self._trailing_error:
                break
        else:
            if decompressor.needs_input:
                rawblock = self._fp.read(_streams.BUFFER_SIZE)
                if not rawblock:
                    raise EOFError("Compressed file ended before the end-of-stream marker was reached")
            else:
                rawblock = b""
            data = decompressor.decompress(rawblock, size)
        if data:
            break

    if not data:
        self._eof = True
        self._size = self._pos
        return b""

    self._pos += len(data)
    return data


def install_candidate(variant: str) -> None:
    if variant == "common_case_split":
        _streams.DecompressReader.read = candidate_common_case_split
        return
    raise ValueError(f"unknown variant: {variant}")


def restore_original() -> None:
    _streams.DecompressReader.read = ORIGINAL_READ
