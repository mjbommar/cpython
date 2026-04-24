import pickletools


ORIGINAL_GENOPS = pickletools._genops
STOP_ORD = ord(".")
BYTE_TO_OPCODE = [None] * 256
for _code, _opcode in pickletools.code2op.items():
    BYTE_TO_OPCODE[ord(_code)] = _opcode


def candidate_genops_byte_table(data, yield_end_pos=False):
    if isinstance(data, pickletools.bytes_types):
        data = pickletools.io.BytesIO(data)

    read = data.read
    getpos = data.tell if hasattr(data, "tell") else None
    if getpos is None:
        return _candidate_genops_without_tell(read, data, yield_end_pos)
    return _candidate_genops_with_tell(read, data, getpos, yield_end_pos)


def _candidate_genops_with_tell(read, data, getpos, yield_end_pos):
    if yield_end_pos:
        while True:
            pos = getpos()
            code = read(1)
            if not code:
                raise ValueError("pickle exhausted before seeing STOP")
            opcode = BYTE_TO_OPCODE[code[0]]
            if opcode is None:
                raise ValueError(
                    "at position %s, opcode %r unknown" % (pos, code)
                )
            opcode_arg = opcode.arg
            arg = None if opcode_arg is None else opcode_arg.reader(data)
            yield opcode, arg, pos, getpos()
            if code[0] == STOP_ORD:
                assert opcode.name == "STOP"
                break
    else:
        while True:
            pos = getpos()
            code = read(1)
            if not code:
                raise ValueError("pickle exhausted before seeing STOP")
            opcode = BYTE_TO_OPCODE[code[0]]
            if opcode is None:
                raise ValueError(
                    "at position %s, opcode %r unknown" % (pos, code)
                )
            opcode_arg = opcode.arg
            arg = None if opcode_arg is None else opcode_arg.reader(data)
            yield opcode, arg, pos
            if code[0] == STOP_ORD:
                assert opcode.name == "STOP"
                break


def _candidate_genops_without_tell(read, data, yield_end_pos):
    pos = None
    if yield_end_pos:
        while True:
            code = read(1)
            if not code:
                raise ValueError("pickle exhausted before seeing STOP")
            opcode = BYTE_TO_OPCODE[code[0]]
            if opcode is None:
                raise ValueError(
                    "at position %s, opcode %r unknown" % ("<unknown>", code)
                )
            opcode_arg = opcode.arg
            arg = None if opcode_arg is None else opcode_arg.reader(data)
            yield opcode, arg, pos, pos
            if code[0] == STOP_ORD:
                assert opcode.name == "STOP"
                break
    else:
        while True:
            code = read(1)
            if not code:
                raise ValueError("pickle exhausted before seeing STOP")
            opcode = BYTE_TO_OPCODE[code[0]]
            if opcode is None:
                raise ValueError(
                    "at position %s, opcode %r unknown" % ("<unknown>", code)
                )
            opcode_arg = opcode.arg
            arg = None if opcode_arg is None else opcode_arg.reader(data)
            yield opcode, arg, pos
            if code[0] == STOP_ORD:
                assert opcode.name == "STOP"
                break


def install_candidate(variant="byte_table"):
    if variant != "byte_table":
        raise ValueError(f"unknown variant: {variant}")
    pickletools._genops = candidate_genops_byte_table


def restore_original():
    pickletools._genops = ORIGINAL_GENOPS
