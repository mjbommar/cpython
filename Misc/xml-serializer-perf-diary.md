# XML Serializer Experiment Diary

Branch: `exp-xml/serializer-fastpaths`

## Goal

Build a serializer-first XML experiment branch that follows the existing perf process:

1. isolate the work on its own branch
2. define a focused benchmark corpus
3. keep correctness guardrails tight
4. measure before deciding whether to broaden the design

## Hypothesis

`xml_etree_process` is dominated by Python-side XML serialization, not parsing or `ElementPath`.

The first experiment is therefore:

- add a private `_elementtree` fast path for exact built-in `Element` trees
- serialize into a single `str` with `PyUnicodeWriter`
- bypass `_namespaces()` and the recursive Python `_serialize_xml()` path when no namespaces or dynamic XML features are involved

## Scope

In scope:

- exact built-in `Element` trees
- XML method only
- no `default_namespace`
- no namespace-qualified names
- no comment / PI / QName / subclass fast path

Out of scope for this branch:

- `ElementPath` acceleration
- namespace-aware serializer acceleration
- HTML / text / C14N serialization
- alternate tree storage or an `xml.ctree` split API

## Guardrails

The C fast path must fall back to the existing Python serializer when it sees:

- subclasses of `Element`
- namespace-qualified tags or attribute names
- comments or processing instructions
- non-string text / tail / attribute values
- any unsupported dynamic shape

## Benchmark Plan

Artifacts live in `Misc/xml-serializer-perf-data/`.

Primary checks:

- focused serializer benchmark for `root` and transformed result trees
- `pyperformance` `xml_etree_process`

Correctness checks:

- `test_xml_etree`
- `test_xml_etree_c`

## Status

Implemented:

- private `_elementtree._serialize_xml_exact()` helper returning `None` to request Python fallback
- `ElementTree.write()` dispatch into the helper for the common XML/no-namespace path
- focused benchmark script and README scaffold

Pending:

- build + run tests
- collect initial serializer and `pyperformance` results
- decide whether to extend into namespace-aware or query-path experiments

## Initial Results

Date: `2026-04-19`

Validation:

- `./python -m test -j4 test_xml_etree test_xml_etree_c` -> pass

Focused serializer benchmark (`xml_serializer_bench.py`, 100 iterations, 9 repeats):

- `serialize-root`: `910.748 ms` -> `43.363 ms` (`-95.24%`)
- `serialize-result`: `2299.358 ms` -> `165.061 ms` (`-92.82%`)
- `process`: `2715.070 ms` -> `600.387 ms` (`-77.89%`)

`pyperformance run --fast --benchmarks xml_etree`:

- `xml_etree_generate`: `108 ms +- 1 ms` -> `33 ms +- 1 ms` (`3.27x faster`)
- `xml_etree_iterparse`: `101 ms +- 2 ms` -> `104 ms +- 3 ms` (`1.03x slower`)
- `xml_etree_parse`: `160 ms +- 3 ms` -> `144 ms +- 4 ms` (`1.11x faster`)
- `xml_etree_process`: `75.0 ms +- 1.1 ms` -> `15.1 ms +- 0.4 ms` (`4.97x faster`)

## Notes

- The first implementation broke `tostringlist()` chunking by collapsing the
  body into one write. The fix was to keep the Python serializer for
  `_ListDataStream`.
- The fast path only targets exact built-in trees with simple XML shapes, so
  namespace-heavy or dynamic workloads still need separate experiments.

## Next Questions

1. Should the serializer fast path learn namespace-aware tags and attributes?
2. Is there a second worthwhile branch for common `ElementPath` patterns like
   `.//tag` and `.//a/b`?
3. Should we add a second exact-tree path that writes bytes directly for binary
   outputs instead of producing a Unicode buffer first?
