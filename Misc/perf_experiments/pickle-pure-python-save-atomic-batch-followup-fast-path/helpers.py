from __future__ import annotations

import pickle


ORIGINAL_BATCH_APPENDS_EXACT = pickle._Pickler._batch_appends_exact


def _specialized_atomic_batch(self, obj, value_type, save_method):
    n = len(obj)
    if type(self) is not pickle._Pickler or n == 0 or type(obj[0]) is not value_type:
        return ORIGINAL_BATCH_APPENDS_EXACT(self, obj)

    for item in obj[1:]:
        if type(item) is not value_type:
            return ORIGINAL_BATCH_APPENDS_EXACT(self, obj)

    write = self.write
    batch_size = self._BATCHSIZE
    idx = 0
    while True:
        remaining = n - idx
        if remaining <= 0:
            return
        if remaining == 1:
            try:
                save_method(self, obj[idx])
            except BaseException as exc:
                exc.add_note(f'when serializing {type(obj).__name__} item {idx}')
                raise
            write(pickle.APPEND)
            return
        batch = remaining if remaining < batch_size else batch_size
        snapshot = obj[idx:idx + batch]
        write(pickle.MARK)
        i = idx
        for x in snapshot:
            try:
                save_method(self, x)
            except BaseException as exc:
                exc.add_note(f'when serializing {type(obj).__name__} item {i}')
                raise
            i += 1
        write(pickle.APPENDS)
        idx = i


def candidate_exact_bool_lists(self, obj):
    return _specialized_atomic_batch(self, obj, bool, pickle._Pickler.save_bool)


def candidate_exact_str_lists(self, obj):
    return _specialized_atomic_batch(self, obj, str, pickle._Pickler.save_str)


def candidate_exact_bytes_lists(self, obj):
    return _specialized_atomic_batch(self, obj, bytes, pickle._Pickler.save_bytes)


def candidate_exact_atomic_lists(self, obj):
    if obj:
        item_type = type(obj[0])
        if item_type is bool:
            return _specialized_atomic_batch(self, obj, bool, pickle._Pickler.save_bool)
        if item_type is str:
            return _specialized_atomic_batch(self, obj, str, pickle._Pickler.save_str)
        if item_type is bytes:
            return _specialized_atomic_batch(self, obj, bytes, pickle._Pickler.save_bytes)
    return ORIGINAL_BATCH_APPENDS_EXACT(self, obj)


def install_candidate(variant="exact_bool_lists"):
    if variant == "exact_bool_lists":
        pickle._Pickler._batch_appends_exact = candidate_exact_bool_lists
    elif variant == "exact_str_lists":
        pickle._Pickler._batch_appends_exact = candidate_exact_str_lists
    elif variant == "exact_bytes_lists":
        pickle._Pickler._batch_appends_exact = candidate_exact_bytes_lists
    elif variant == "exact_atomic_lists":
        pickle._Pickler._batch_appends_exact = candidate_exact_atomic_lists
    else:
        raise ValueError(f"unknown variant: {variant}")


def restore_original():
    pickle._Pickler._batch_appends_exact = ORIGINAL_BATCH_APPENDS_EXACT
