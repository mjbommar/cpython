# XML escape scan fast paths

Branch: `exp-xml/escape-scan-fastpaths-mainline`
Base commit: `9fd8c170f49c086ff331f276e52d6dd8914a12e7`
Manifest: `Misc/perf_experiments/xml-escape-scan-fastpaths/experiment.json`

## Goal

Archetype: common-case split/control-flow lifting, following the StringZilla fast-rejection-before-exact-handling pattern. XML serializers often emit text and attributes without escapable characters; a single cheap common-case escape scan may reduce repeated membership/replace work in ElementTree serialization without changing exact escaping behavior.

## Targets

- Lib/xml/etree/ElementTree.py:1018 _escape_cdata
- Lib/xml/etree/ElementTree.py:1034 _escape_attrib
- Lib/xml/etree/ElementTree.py:860 _serialize_xml

## Success Criteria

- Improve total runtime on XML serialization-focused microbenchmarks and do not regress pyperformance xml_etree_generate/xml_etree_process or focused ElementTree tests.

## Input Evidence

- Profiles:
  - `benchmarks/results/baseline-profile.txt`
  - `benchmarks/results/e3-profile.txt`
  - `benchmarks/results/e4-profile.txt`
- Usage scan:
  - Serializer is pure Python in `Lib/xml/etree/ElementTree.py`; `_elementtree.c` provides accelerated element/parser objects but not the serializer loop.
  - Baseline clean-tree profile: `_serialize_xml` 1.461s tottime, `isinstance` 0.536s, `_namespaces` 0.532s, `_escape_attrib` 0.215s, `_escape_cdata` 0.066s.
- Initial benchmark corpus:
  - `benchmarks/bench_xml_escape.py` direct escape helper cases plus `ElementTree.tostring()` clean/escaped tree cases.
  - pyperformance fast `xml_etree` smoke run through `Misc/ecosystem_benchmarks/run_pyperformance.py`.
- Guardrails:
  - `./python -m test test_xml_etree test_xml_etree_c -j1`
  - `git diff --check`

## Candidate Ledger

### E1

Status: replaced by E2/E3.

Thesis:

- Add exact-`str` common-case splits before repeated `QName` `isinstance()` checks in `_namespaces`, `_serialize_xml`, and `_serialize_html`.

Result:

- First focused run: `tostring()` clean tree -20.07%, escaped tree -17.01%; profile showed `isinstance` tottime dropping from 0.536s to 0.043s.

Decision:

- Keep and extend to the remaining text check.

### E2

Status: replaced by E3.

Thesis:

- Apply the same exact-`str` guard to `_namespaces` element text QName detection.

Result:

- Focused run: `tostring()` clean tree -21.37%, escaped tree -17.59%.

Decision:

- Keep and test adjacent serializer list-copy cost.

### E3

Status: replaced by E4.

Thesis:

- Preserve the QName common-case split and avoid `list(elem.items())` when the C accelerator already returned an exact list; retain the old snapshot behavior for non-list `items()` results.

Result:

- Same-worktree focused A/B: geomean -9.56%; `tostring()` clean tree -18.53%, escaped tree -18.06%.
- pyperformance fast `xml_etree`: `xml_etree_generate` 112 ms -> 107 ms (1.05x faster), `xml_etree_process` 79.0 ms -> 70.3 ms (1.12x faster); parse/iterparse not significant.

Decision:

- Keep the shape, but replace `obj.__class__` checks with `type(obj)` to avoid invoking user-defined attribute lookup on unusual objects.

### E4

Status: accepted branch-local.

Thesis:

- Use exact `type(obj) is str` / `type(items) is list` fast paths for the dominant serializer shapes, leaving QName, subclasses, and non-list item views on the original slower paths.

Result:

- Focused A/B against the saved same-worktree baseline: geomean -9.50%; `tostring()` clean tree -17.34%, escaped tree -17.73%.
- pyperformance fast `xml_etree`: parse 1.05x faster, iterparse 1.07x faster, generate 1.12x faster, process 1.15x faster; geomean 1.10x faster.

Decision:

- Accept. This is a StringZilla-style fast rejection/common-case split at the serializer type-shape layer rather than in the byte scanner: exact `str` and exact list attribute snapshots are overwhelmingly common, while QName/subclass behavior remains on the slow path.

## Validation

- Focused tests:
  - `./python -m test test_xml_etree test_xml_etree_c -j1`: passed, 462 tests run, 12 skipped.
- Full suite:
  - Not run for this branch-local proof.
- Ecosystem / third-party:
  - pyperformance fast `xml_etree` A/B completed; final compare output in `benchmarks/results/pyperformance-compare-e4.txt`.

## Acceptance Decision

- Decision: branch-local accept; ready for stacked validation.
- Accepted commit:
- Stacked winner commit:

## Notes

- Keep rejected ideas here too so the branch remains useful research.
- Rejected escape-only variants before source patching: no-special fast-reject and `str.translate()` shapes did not improve clean common cases enough; `translate()` was materially slower on long strings.
