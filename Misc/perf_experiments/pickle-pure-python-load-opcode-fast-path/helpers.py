from __future__ import annotations

import pickle


ORIGINAL_LOAD = pickle._Unpickler.load


def candidate_inline_hot_opcodes(self):
    if not hasattr(self, "_file_read"):
        raise pickle.UnpicklingError(
            "Unpickler.__init__() was not called by "
            f"{self.__class__.__name__}.__init__()"
        )

    self._unframer = pickle._Unframer(self._file_read, self._file_readline)
    self.read = self._unframer.read
    self.readinto = self._unframer.readinto
    self.readline = self._unframer.readline
    self.metastack = []
    self.stack = []
    self.append = self.stack.append
    self.proto = 0

    read = self.read
    dispatch = self.dispatch
    memo = self.memo
    metastack = self.metastack
    stack = self.stack
    append = self.append
    unpack = pickle.unpack

    try:
        while True:
            key = read(1)
            if not key:
                raise EOFError
            code = key[0]

            if code == pickle.BININT1[0]:
                append(read(1)[0])
                continue
            if code == pickle.BININT2[0]:
                append(unpack("<H", read(2))[0])
                continue
            if code == pickle.SHORT_BINUNICODE[0]:
                length = read(1)[0]
                append(str(read(length), "utf-8", "surrogatepass"))
                continue
            if code == pickle.TUPLE1[0]:
                stack[-1] = (stack[-1],)
                continue
            if code == pickle.TUPLE2[0]:
                stack[-2:] = [(stack[-2], stack[-1])]
                continue
            if code == pickle.TUPLE3[0]:
                stack[-3:] = [(stack[-3], stack[-2], stack[-1])]
                continue
            if code == pickle.EMPTY_TUPLE[0]:
                append(())
                continue
            if code == pickle.EMPTY_LIST[0]:
                append([])
                continue
            if code == pickle.EMPTY_DICT[0]:
                append({})
                continue
            if code == pickle.NEWTRUE[0]:
                append(True)
                continue
            if code == pickle.NEWFALSE[0]:
                append(False)
                continue
            if code == pickle.MARK[0]:
                metastack.append(stack)
                stack = []
                self.stack = stack
                append = stack.append
                self.append = append
                continue
            if code == pickle.BINGET[0]:
                append(memo[read(1)[0]])
                continue
            if code == pickle.LONG_BINGET[0]:
                append(memo[unpack("<I", read(4))[0]])
                continue
            if code == pickle.MEMOIZE[0]:
                memo[len(memo)] = stack[-1]
                continue
            if code == pickle.APPENDS[0]:
                items = stack
                stack = metastack.pop()
                self.stack = stack
                append = stack.append
                self.append = append
                list_obj = stack[-1]
                if isinstance(list_obj, list):
                    list_obj.extend(items)
                else:
                    for item in items:
                        list_obj.append(item)
                continue
            if code == pickle.SETITEMS[0]:
                items = stack
                stack = metastack.pop()
                self.stack = stack
                append = stack.append
                self.append = append
                dict_obj = stack[-1]
                for i in range(0, len(items), 2):
                    dict_obj[items[i]] = items[i + 1]
                continue
            if code == pickle.STOP[0]:
                raise pickle._Stop(stack.pop())

            dispatch[code](self)
            stack = self.stack
            append = self.append
    except pickle._Stop as stopinst:
        return stopinst.value


def install_candidate(variant: str) -> None:
    if variant == "inline_hot_opcodes":
        pickle._Unpickler.load = candidate_inline_hot_opcodes
        return
    raise ValueError(f"unknown variant: {variant}")


def restore_original() -> None:
    pickle._Unpickler.load = ORIGINAL_LOAD
