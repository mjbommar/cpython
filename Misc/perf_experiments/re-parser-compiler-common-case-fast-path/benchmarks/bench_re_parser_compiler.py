#!/usr/bin/env python3
"""Focused benchmark for re parser/compiler common-case fast paths."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import traceback
from email import feedparser, generator, utils as email_utils
from re import _compiler, _parser
from test import re_tests

import glob
import pydoc


_ORIG_COMPILE = _compiler.compile
_ORIG_STATE_INIT = _parser.State.__init__
_ORIG_OPENGROUP = _parser.State.opengroup
_ORIG_PARSE_SUB = _parser._parse_sub
_EMPTY_INDEXGROUP = (None,)
_EMPTY_GROUPDICT = {}

_STDLIB_PATTERN_CORPUS = [
    (r"\s+", _compiler.SRE_FLAG_ASCII),
    (r"\n\n\n+", 0),
    (r"-\.?\d", 0),
    (traceback._ANSI_ESCAPE_SEQUENCE.pattern, traceback._ANSI_ESCAPE_SEQUENCE.flags),
    (glob.magic_check.pattern, glob.magic_check.flags),
    (glob.magic_check_bytes.pattern, glob.magic_check_bytes.flags),
    (pydoc._re_stripid.pattern, pydoc._re_stripid.flags),
    (email_utils.specialsre.pattern, email_utils.specialsre.flags),
    (email_utils.escapesre.pattern, email_utils.escapesre.flags),
    (feedparser.headerRE.pattern, feedparser.headerRE.flags),
    (generator.fcre.pattern, generator.fcre.flags),
]

_RE_TESTS_BENCHMARKS = [(pattern, 0) for pattern, _ in re_tests.benchmarks]

_MICRO_CASES = {
    "R1_literal": (r"abc", 0),
    "R2_literal_bytes": (b"abc", 0),
    "R3_charclass": (r"[A-Za-z_][A-Za-z0-9_]*", 0),
    "R4_captures": (r"(foo)(bar)?(baz)*", 0),
    "R5_named_groups": (r"(?P<first>foo)(?P<second>bar)?(?P<third>baz)*", 0),
    "R6_branch_prefix": (r"foobar|foobaz|fooquux|foospam", 0),
    "R7_inline_flags": (r"(?imx:foo[ ]+bar)", 0),
    "R8_lookaround": (r"(?<=abc)(foo|bar)(?!baz)", 0),
    "R9_backref": (r"(?P<word>\w+)-(?P=word)", 0),
    "R10_alternation": (r"foo|bar|baz|quux|spam|eggs", 0),
    "R11_branch_repeat": (r"(ab|ac|ad)+z", 0),
    "R12_charset_branch": (r"[abc]|[def]|g", 0),
}


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


class Variant:
    def __init__(self, name: str):
        self.name = name
        self._orig_compile = None
        self._orig_state_init = None
        self._orig_opengroup = None
        self._orig_parse_sub = None

    def __enter__(self):
        if self.name == "runtime":
            return
        if self.name == "groupindex_fastpath":
            self._orig_compile = _compiler.compile
            _compiler.compile = _candidate_compile_groupindex_fastpath
            return
        if self.name == "lazy_groupdict":
            self._orig_state_init = _parser.State.__init__
            self._orig_opengroup = _parser.State.opengroup
            _parser.State.__init__ = _candidate_state_init_lazy_groupdict
            _parser.State.opengroup = _candidate_opengroup_lazy_groupdict
            return
        if self.name == "parse_sub_data_fastpath":
            self._orig_parse_sub = _parser._parse_sub
            _parser._parse_sub = _candidate_parse_sub_data_fastpath
            return
        else:
            raise ValueError(f"unknown variant: {self.name}")

    def __exit__(self, exc_type, exc, tb):
        if self._orig_compile is not None:
            _compiler.compile = self._orig_compile
        if self._orig_state_init is not None:
            _parser.State.__init__ = self._orig_state_init
        if self._orig_opengroup is not None:
            _parser.State.opengroup = self._orig_opengroup
        if self._orig_parse_sub is not None:
            _parser._parse_sub = self._orig_parse_sub


def _measure(label: str, func, *, loops: int, repeat: int) -> dict[str, object]:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        for _ in range(loops):
            func()
        elapsed = time.perf_counter() - start
        samples.append(elapsed / loops)
    return {
        "label": label,
        "loops": loops,
        "repeat": repeat,
        "samples_ns": [round(sample * 1e9, 1) for sample in samples],
        "best_ns": round(min(samples) * 1e9, 1),
        "mean_ns": round(statistics.mean(samples) * 1e9, 1),
    }


def _bench_compile(pattern, flags):
    _compiler.compile(pattern, flags)


def _bench_corpus(corpus):
    for pattern, flags in corpus:
        _compiler.compile(pattern, flags)


def run_benchmarks(*, loops: int, repeat: int) -> dict[str, object]:
    results = {}

    for key, (pattern, flags) in _MICRO_CASES.items():
        case_loops = loops
        if key in {"R5_named_groups", "R8_lookaround"}:
            case_loops = max(1000, loops // 2)
        if key == "R9_backref":
            case_loops = max(1000, loops // 3)
        results[key] = _measure(
            key,
            lambda pattern=pattern, flags=flags: _bench_compile(pattern, flags),
            loops=case_loops,
            repeat=repeat,
        )

    results["R10_stdlib_compile_corpus"] = _measure(
        "stdlib compile corpus",
        lambda: _bench_corpus(_STDLIB_PATTERN_CORPUS),
        loops=max(150, loops // 20),
        repeat=repeat,
    )
    results["R11_re_tests_compile_corpus"] = _measure(
        "re_tests benchmark compile corpus",
        lambda: _bench_corpus(_RE_TESTS_BENCHMARKS),
        loops=max(150, loops // 20),
        repeat=repeat,
    )
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("runtime", "groupindex_fastpath", "lazy_groupdict", "parse_sub_data_fastpath"),
        default="runtime",
    )
    parser.add_argument("--loops", type=int, default=3000)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    with Variant(ns.variant):
        for _ in range(200):
            for pattern, flags in _MICRO_CASES.values():
                _compiler.compile(pattern, flags)
            _bench_corpus(_STDLIB_PATTERN_CORPUS)
            _bench_corpus(_RE_TESTS_BENCHMARKS)

        results = {
            "variant": ns.variant,
            "benchmarks": run_benchmarks(loops=ns.loops, repeat=ns.repeat),
        }

    if ns.json:
        print(json.dumps(results, indent=2, sort_keys=True))
        return

    print(f"[variant={ns.variant}]")
    for key in sorted(results["benchmarks"]):
        result = results["benchmarks"][key]
        print(
            f"{key}: best={result['best_ns']} ns "
            f"mean={result['mean_ns']} ns samples={result['samples_ns']}"
        )


if __name__ == "__main__":
    main()
