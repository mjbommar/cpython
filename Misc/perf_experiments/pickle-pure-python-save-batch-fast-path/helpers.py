import pickle


ORIGINAL_BATCH_APPENDS_EXACT = pickle._Pickler._batch_appends_exact


def _batch_appends_exact_ints(self, obj, *, min_size):
    n = len(obj)
    if n <= min_size:
        return ORIGINAL_BATCH_APPENDS_EXACT(self, obj)
    if type(self) is not pickle._Pickler or n == 0 or type(obj[0]) is not int:
        return ORIGINAL_BATCH_APPENDS_EXACT(self, obj)

    for item in obj[1:]:
        if type(item) is not int:
            return ORIGINAL_BATCH_APPENDS_EXACT(self, obj)

    save_long = pickle._Pickler.save_long
    write = self.write
    batch_size = self._BATCHSIZE
    idx = 0
    while True:
        remaining = n - idx
        if remaining <= 0:
            return
        if remaining == 1:
            save_long(self, obj[idx])
            write(pickle.APPEND)
            return
        batch = remaining if remaining < batch_size else batch_size
        end = idx + batch
        write(pickle.MARK)
        while idx < end:
            save_long(self, obj[idx])
            idx += 1
        write(pickle.APPENDS)


def candidate_batch_appends_exact_ints(self, obj):
    return _batch_appends_exact_ints(self, obj, min_size=0)


def candidate_batch_appends_exact_ints_min8(self, obj):
    return _batch_appends_exact_ints(self, obj, min_size=8)


def install_candidate(variant="exact_int_lists"):
    if variant == "exact_int_lists":
        pickle._Pickler._batch_appends_exact = candidate_batch_appends_exact_ints
    elif variant == "exact_int_lists_min8":
        pickle._Pickler._batch_appends_exact = candidate_batch_appends_exact_ints_min8
    else:
        raise ValueError(f"unknown variant: {variant}")


def restore_original():
    pickle._Pickler._batch_appends_exact = ORIGINAL_BATCH_APPENDS_EXACT
