import pickle


ORIGINAL_SAVE_TUPLE = pickle._Pickler.save_tuple
ORIGINAL_DISPATCH_TUPLE = pickle._Pickler.dispatch[tuple]


def _candidate_save_tuple_exact_ints(self, obj):
    if type(self) is pickle._Pickler and obj and type(obj[0]) is int:
        for item in obj[1:]:
            if type(item) is not int:
                break
        else:
            save_long = self.save_long
            n = len(obj)
            if n <= 3 and self.proto >= 2:
                for i, element in enumerate(obj):
                    try:
                        save_long(element)
                    except BaseException as exc:
                        exc.add_note(f'when serializing {type(obj).__name__} item {i}')
                        raise
                self.write(pickle._tuplesize2code[n])
                self.memoize(obj)
                return

            write = self.write
            write(pickle.MARK)
            for i, element in enumerate(obj):
                try:
                    save_long(element)
                except BaseException as exc:
                    exc.add_note(f'when serializing {type(obj).__name__} item {i}')
                    raise
            write(pickle.TUPLE)
            self.memoize(obj)
            return

    return ORIGINAL_SAVE_TUPLE(self, obj)


def install_candidate(variant="exact_int_tuples"):
    if variant != "exact_int_tuples":
        raise ValueError(f"unknown variant: {variant}")
    pickle._Pickler.save_tuple = _candidate_save_tuple_exact_ints
    pickle._Pickler.dispatch[tuple] = _candidate_save_tuple_exact_ints


def restore_original():
    pickle._Pickler.save_tuple = ORIGINAL_SAVE_TUPLE
    pickle._Pickler.dispatch[tuple] = ORIGINAL_DISPATCH_TUPLE
