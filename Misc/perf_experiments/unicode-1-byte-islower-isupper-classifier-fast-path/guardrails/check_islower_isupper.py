"""Semantic guardrails for str.islower()/str.isupper() fast paths."""

from __future__ import annotations


LOWER_1BYTE = (
    0x0,
    0x7FFFFFE00000000,
    0x420040000000000,
    0xFF7FFFFF80000000,
)
UPPER_1BYTE = (
    0x0,
    0x7FFFFFE,
    0x0,
    0x7F7FFFFF,
)


def contains(words: tuple[int, int, int, int], ch: int) -> bool:
    return bool(words[ch >> 6] & (1 << (ch & 63)))


def check_1byte_membership() -> None:
    for ch in range(256):
        s = chr(ch)
        assert s.islower() == contains(LOWER_1BYTE, ch), (ch, s, "islower")
        assert s.isupper() == contains(UPPER_1BYTE, ch), (ch, s, "isupper")


def check_multichar_semantics() -> None:
    lower = "".join(chr(ch) for ch in range(256) if not chr(ch).isupper())
    upper = "".join(chr(ch) for ch in range(256) if not chr(ch).islower())
    assert lower.islower()
    assert not (lower + "A").islower()
    assert upper.isupper()
    assert not (upper + "a").isupper()
    assert not "".islower()
    assert not "".isupper()
    assert not "12345".islower()
    assert not "12345".isupper()
    assert "naïve à la mode".islower()
    assert not "naïve À la mode".islower()
    assert "\u2167".isupper()
    assert "\u2177".islower()
    assert "\U00010401".isupper()
    assert "\U00010429".islower()


def main() -> None:
    check_1byte_membership()
    check_multichar_semantics()
    print("islower/isupper guardrails ok")


if __name__ == "__main__":
    main()
