import pickle


ORIGINAL_UNFRAMER_READ = pickle._Unframer.read


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


def install_candidate():
    pickle._Unframer.read = candidate_unframer_read


def restore_original():
    pickle._Unframer.read = ORIGINAL_UNFRAMER_READ
