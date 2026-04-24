#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import io
import re
from re import _compiler, _parser


_ORIG_COMPILE = _compiler.compile
_ORIG_STATE_INIT = _parser.State.__init__
_ORIG_OPENGROUP = _parser.State.opengroup
_ORIG_PARSE_SUB = _parser._parse_sub
_EMPTY_INDEXGROUP = (None,)
_EMPTY_GROUPDICT = {}


def _candidate_compile_groupindex_fastpath(p, flags=0):
    if _compiler.isstring(p):
        pattern = p
        p = _parser.parse(p, flags)
    else:
        pattern = None

    code = _compiler._code(p, flags)

    if flags & _compiler.SRE_FLAG_DEBUG:
        print()
        _compiler.dis(code)

    groups = p.state.groups
    groupindex = p.state.groupdict
    if groupindex:
        indexgroup = [None] * groups
        for name, index in groupindex.items():
            indexgroup[index] = name
        indexgroup = tuple(indexgroup)
    elif groups == 1:
        indexgroup = _EMPTY_INDEXGROUP
    else:
        indexgroup = (None,) * groups

    return _compiler._sre.compile(
        pattern,
        flags | p.state.flags,
        code,
        groups - 1,
        groupindex,
        indexgroup,
    )


def _candidate_state_init_lazy_groupdict(self):
    self.flags = 0
    self.groupdict = _EMPTY_GROUPDICT
    self.groupwidths = [None]
    self.lookbehindgroups = None
    self.grouprefpos = {}


def _candidate_opengroup_lazy_groupdict(self, name=None):
    gid = self.groups
    self.groupwidths.append(None)
    if self.groups > _parser.MAXGROUPS:
        raise _parser.error("too many groups")
    if name is not None:
        groupdict = self.groupdict
        ogid = groupdict.get(name, None)
        if ogid is not None:
            raise _parser.error(
                "redefinition of group name %r as group %d; was group %d"
                % (name, gid, ogid)
            )
        if groupdict is _EMPTY_GROUPDICT:
            groupdict = self.groupdict = {}
        groupdict[name] = gid
    return gid


def _candidate_parse_sub_data_fastpath(source, state, verbose, nested):
    items = []
    itemsappend = items.append
    sourcematch = source.match
    while True:
        itemsappend(_parser._parse(source, state, verbose, nested + 1,
                                   not nested and not items))
        if not sourcematch("|"):
            break
        if not nested:
            verbose = state.flags & _compiler.SRE_FLAG_VERBOSE

    if len(items) == 1:
        return items[0]

    subpattern = _parser.SubPattern(state)

    while True:
        prefix = None
        for item in items:
            item_data = item.data
            if not item_data:
                break
            head = item_data[0]
            if prefix is None:
                prefix = head
            elif head != prefix:
                break
        else:
            for item in items:
                del item.data[0]
            subpattern.append(prefix)
            continue
        break

    charset = []
    for item in items:
        item_data = item.data
        if len(item_data) != 1:
            break
        op, av = item_data[0]
        if op is _parser.LITERAL:
            charset.append((op, av))
        elif op is _parser.IN and av[0][0] is not _parser.NEGATE:
            charset.extend(av)
        else:
            break
    else:
        subpattern.append((_parser.IN, _parser._uniq(charset)))
        return subpattern

    subpattern.append((_parser.BRANCH, (None, items)))
    return subpattern


@contextlib.contextmanager
def _patched_variant(name):
    orig_compile = _compiler.compile
    orig_state_init = _parser.State.__init__
    orig_opengroup = _parser.State.opengroup
    orig_parse_sub = _parser._parse_sub
    if name == "groupindex_fastpath":
        _compiler.compile = _candidate_compile_groupindex_fastpath
    elif name == "lazy_groupdict":
        _parser.State.__init__ = _candidate_state_init_lazy_groupdict
        _parser.State.opengroup = _candidate_opengroup_lazy_groupdict
    elif name == "parse_sub_data_fastpath":
        _parser._parse_sub = _candidate_parse_sub_data_fastpath
    else:
        raise ValueError(name)
    try:
        yield
    finally:
        _compiler.compile = orig_compile
        _parser.State.__init__ = orig_state_init
        _parser.State.opengroup = orig_opengroup
        _parser._parse_sub = orig_parse_sub


def _match_snapshot(compiled, sample):
    match = compiled.search(sample)
    fullmatch = compiled.fullmatch(sample)
    return {
        "pattern": compiled.pattern,
        "flags": compiled.flags,
        "groups": compiled.groups,
        "groupindex": dict(compiled.groupindex),
        "search_span": None if match is None else match.span(),
        "search_groups": None if match is None else match.groups(),
        "search_groupdict": None if match is None else match.groupdict(),
        "fullmatch_span": None if fullmatch is None else fullmatch.span(),
        "findall": compiled.findall(sample),
        "split": compiled.split(sample),
    }


def _compile_snapshot(pattern, flags, sample):
    compiled = re.compile(pattern, flags)
    return _match_snapshot(compiled, sample)


def _error_snapshot(pattern, flags):
    try:
        re.compile(pattern, flags)
    except Exception as exc:
        return {
            "type": type(exc).__name__,
            "message": str(exc),
            "pos": getattr(exc, "pos", None),
        }
    raise AssertionError(f"expected compile error for {pattern!r}")


def main():
    cases = [
        ("literal", r"abc", 0, "xxabcxx"),
        ("literal_bytes", b"abc", 0, b"xxabcxx"),
        ("captures", r"(foo)(bar)?(baz)*", 0, "foobarbazbaz"),
        ("named_groups", r"(?P<first>foo)(?P<second>bar)?(?P<third>baz)*", 0, "foobarbaz"),
        ("branch_prefix", r"foobar|foobaz|fooquux|foospam", 0, "xxfoobazyy"),
        ("alternation", r"foo|bar|baz|quux|spam|eggs", 0, "xxspamyy"),
        ("inline_flags", r"(?imx:foo[ ]+bar)", 0, "FOO   BAR"),
        ("lookaround", r"(?<=abc)(foo|bar)(?!baz)", 0, "abcfooq"),
        ("backref", r"(?P<word>\w+)-(?P=word)", 0, "abc-abc"),
        ("branch_repeat", r"(ab|ac|ad)+z", 0, "abacz"),
        ("charset_branch", r"[abc]|[def]|g", 0, "e"),
        ("conditional", r"(?P<g1>a)(?P<g2>b)?((?(g2)c|d))", 0, "abc"),
    ]
    error_cases = [
        (r"(?P<a>)(?P<a>)", 0),
        (r"(?P=a)", 0),
        (r"(?(2)a)", 0),
        (r"(?i", 0),
        (br"(?u)\w", 0),
    ]

    baseline = {name: _compile_snapshot(pattern, flags, sample) for name, pattern, flags, sample in cases}
    baseline_errors = [_error_snapshot(pattern, flags) for pattern, flags in error_cases]

    for variant in ("groupindex_fastpath", "lazy_groupdict", "parse_sub_data_fastpath"):
        with _patched_variant(variant):
            candidate = {name: _compile_snapshot(pattern, flags, sample) for name, pattern, flags, sample in cases}
            candidate_errors = [_error_snapshot(pattern, flags) for pattern, flags in error_cases]

            capture_a = io.StringIO()
            capture_b = io.StringIO()
            with contextlib.redirect_stdout(capture_a):
                baseline_debug = re.compile(r"(foo|bar)+", re.DEBUG)
            with contextlib.redirect_stdout(capture_b):
                candidate_debug = re.compile(r"(foo|bar)+", re.DEBUG)

        assert baseline == candidate, variant
        assert baseline_errors == candidate_errors, variant
        assert baseline_debug.pattern == candidate_debug.pattern, variant
        assert baseline_debug.flags == candidate_debug.flags, variant
        assert baseline_debug.groups == candidate_debug.groups, variant
        assert dict(baseline_debug.groupindex) == dict(candidate_debug.groupindex), variant
        assert capture_a.getvalue() == capture_b.getvalue(), variant

    immutable = re.compile(r"(?P<first>a)(?P<second>b)")
    for variant in ("groupindex_fastpath", "lazy_groupdict", "parse_sub_data_fastpath"):
        with _patched_variant(variant):
            patched_immutable = re.compile(r"(?P<first>a)(?P<second>b)")
        for compiled in (immutable, patched_immutable):
            try:
                compiled.groupindex["first"] = 9
            except TypeError:
                pass
            else:
                raise AssertionError(f"groupindex should remain immutable: {variant}")

    print("re parser/compiler guardrails: ok")


if __name__ == "__main__":
    main()
