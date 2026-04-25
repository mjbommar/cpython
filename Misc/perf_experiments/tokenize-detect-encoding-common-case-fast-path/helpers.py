from __future__ import annotations

import tokenize


ORIGINAL_DETECT_ENCODING = tokenize.detect_encoding


def candidate_common_case_split(readline):
    cookie_re = tokenize.cookie_re
    blank_re = tokenize.blank_re
    lookup = tokenize.lookup
    bom_utf8 = tokenize.BOM_UTF8
    get_normal_name = tokenize._get_normal_name

    try:
        filename = readline.__self__.name
    except AttributeError:
        filename = None

    bom_found = False
    default = "utf-8"

    def read_or_stop():
        try:
            return readline()
        except StopIteration:
            return b""

    def check(line, encoding):
        if 0 in line:
            raise SyntaxError("source code cannot contain null bytes")
        try:
            line.decode(encoding)
        except UnicodeDecodeError:
            msg = "invalid or missing encoding declaration"
            if filename is not None:
                msg = f"{msg} for {filename!r}"
            raise SyntaxError(msg)

    def find_cookie(line):
        match = cookie_re.match(line)
        if not match:
            return None
        encoding = get_normal_name(match.group(1).decode())
        try:
            lookup(encoding)
        except LookupError:
            if filename is None:
                msg = "unknown encoding: " + encoding
            else:
                msg = f"unknown encoding for {filename!r}: {encoding}"
            raise SyntaxError(msg)

        if bom_found:
            if encoding != "utf-8":
                if filename is None:
                    msg = "encoding problem: utf-8"
                else:
                    msg = f"encoding problem for {filename!r}: utf-8"
                raise SyntaxError(msg)
            encoding += "-sig"
        return encoding

    first = read_or_stop()
    if first.startswith(bom_utf8):
        bom_found = True
        first = first[3:]
        default = "utf-8-sig"
    if not first:
        return default, []

    # Dominant case in the stdlib: the first line is already source code or a
    # docstring opener, so there is no cookie and no need for the blank-line
    # second-line logic.
    if first[:1] not in b"# \t\f\r\n":
        check(first, default)
        return default, [first]

    encoding = find_cookie(first)
    if encoding:
        check(first, encoding)
        return encoding, [first]
    if not blank_re.match(first):
        check(first, default)
        return default, [first]

    second = read_or_stop()
    if not second:
        check(first, default)
        return default, [first]

    encoding = find_cookie(second)
    if encoding:
        check(first + second, encoding)
        return encoding, [first, second]

    check(first + second, default)
    return default, [first, second]


def install_candidate(variant: str) -> None:
    if variant == "common_case_split":
        tokenize.detect_encoding = candidate_common_case_split
        return
    raise ValueError(f"unknown variant: {variant}")


def restore_original() -> None:
    tokenize.detect_encoding = ORIGINAL_DETECT_ENCODING
