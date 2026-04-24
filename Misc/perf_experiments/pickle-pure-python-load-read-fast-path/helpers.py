import pickle


ORIGINAL_UNFRAMER_READ = pickle._Unframer.read
ORIGINAL_CHUNKED_FILE_READ = pickle._Unframer._chunked_file_read


def candidate_unframer_read(self, n):
    current_frame = self.current_frame
    if current_frame:
        data = current_frame.read(n)
        if not data and n != 0:
            self.current_frame = None
            return self.file_read(n)
        if len(data) < n:
            raise pickle.UnpicklingError("pickle exhausted before end of frame")
        return data
    if n <= pickle._MIN_READ_BUF_SIZE:
        return self.file_read(n)
    return self._chunked_file_read(n)


def candidate_chunked_file_read_join(self, size):
    cursize = min(size, pickle._MIN_READ_BUF_SIZE)
    chunk = self.file_read(cursize)
    if cursize >= size or len(chunk) < cursize:
        return chunk
    chunks = [chunk]
    while cursize < size:
        delta = min(pickle._MIN_READ_BUF_SIZE, size - cursize)
        chunk = self.file_read(delta)
        chunks.append(chunk)
        cursize += delta
        if len(chunk) < delta:
            break
    return b"".join(chunks)


def candidate_chunked_file_read_bytearray(self, size):
    cursize = min(size, pickle._MIN_READ_BUF_SIZE)
    chunk = self.file_read(cursize)
    if cursize >= size or len(chunk) < cursize:
        return chunk
    buf = bytearray(chunk)
    while cursize < size:
        delta = min(pickle._MIN_READ_BUF_SIZE, size - cursize)
        chunk = self.file_read(delta)
        buf.extend(chunk)
        cursize += delta
        if len(chunk) < delta:
            break
    return bytes(buf)


def candidate_chunked_file_read_join_large_only(self, size):
    if size <= 2 * pickle._MIN_READ_BUF_SIZE:
        return ORIGINAL_CHUNKED_FILE_READ(self, size)
    return candidate_chunked_file_read_join(self, size)


def install_candidate(variant="small_read_fast_path"):
    if variant == "small_read_fast_path":
        pickle._Unframer.read = candidate_unframer_read
    elif variant == "chunk_join":
        pickle._Unframer._chunked_file_read = candidate_chunked_file_read_join
    elif variant == "chunk_bytearray":
        pickle._Unframer._chunked_file_read = candidate_chunked_file_read_bytearray
    elif variant == "chunk_join_large_only":
        pickle._Unframer._chunked_file_read = candidate_chunked_file_read_join_large_only
    else:
        raise ValueError(f"unknown variant: {variant}")


def restore_original():
    pickle._Unframer.read = ORIGINAL_UNFRAMER_READ
    pickle._Unframer._chunked_file_read = ORIGINAL_CHUNKED_FILE_READ
