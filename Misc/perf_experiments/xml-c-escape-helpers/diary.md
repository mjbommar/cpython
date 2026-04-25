# XML C escape helpers

Branch: `exp-xml/c-escape-helpers-mainline`
Base commit: `9fd8c170f49c086ff331f276e52d6dd8914a12e7`
Manifest: `Misc/perf_experiments/xml-c-escape-helpers/experiment.json`

## Goal

Archetype: prepared-search/input-shape snapshot plus exact-type gate, following the StringZilla fast-rejection-before-exact-handling pattern. Exact str XML text and attribute fragments can be scanned in C for escapable characters and returned unchanged when clean; only dirty strings allocate and build replacements. Non-str extension behavior remains on the Python slow path.

## Targets

- Lib/xml/etree/ElementTree.py:_escape_cdata
- Lib/xml/etree/ElementTree.py:_escape_attrib
- Modules/_elementtree.c module helpers

## Success Criteria

- Improve XML serialization total runtime on focused ElementTree benchmarks and pyperformance xml_etree without changing ElementTree escaping semantics.

## Input Evidence

- Profiles:
  - `benchmarks/results/baseline-profile.txt`
  - `benchmarks/results/e2-profile.txt`
- Usage scan:
  - Serializer escaping is Python-level in `ElementTree.py`; `_elementtree` can provide private exact-`str` helpers without changing element/parser ownership.
  - Baseline profile: `_escape_attrib` 0.213s and `_escape_cdata` 0.065s tottime inside the clean-tree serialization profile; type-dispatch overhead remains larger but escaping is still measurable.
- Initial benchmark corpus:
  - `benchmarks/bench_xml_c_escape.py` direct escape helper cases plus clean/escaped `ElementTree.tostring()` tree cases.
  - pyperformance fast `xml_etree`.
- Guardrails:
  - exact `str` calls use C helpers; subclasses and non-string extension behavior fall back to the original Python helpers.
  - `./python -m test test_xml_etree test_xml_etree_c -j1`
  - `git diff --check`

## Candidate Ledger

### E1

Status: rejected.

Thesis:

- Add C helpers that scan all Unicode kinds with `PyUnicode_READ()` and build replacements with `PyUnicodeWriter`.

Result:

- Dirty strings improved, but long clean strings regressed badly because generic per-code-point scanning lost to CPython's optimized substring search.
- Example focused result: long clean cdata +623%, long clean attrib +441%; `tostring()` still improved 8-10%.

Decision:

- Reject generic scanning. It violates the StringZilla lesson: the fast rejection layer itself must be cheap.

### E2

Status: accepted branch-local.

Thesis:

- Use `memchr()` for 1-byte strings to find the first escapable byte from the small XML byte set, then allocate/build only after a hit; keep the generic Unicode loop as fallback for wider strings.

Result:

- Serialized same-worktree focused A/B: geomean -27.06%; direct dirty attrib -50.74%; `tostring()` clean tree -8.78%, escaped tree -8.19%.
- pyperformance fast `xml_etree`: `xml_etree_generate` 110 ms -> 107 ms (1.03x faster), `xml_etree_process` 75.4 ms -> 72.7 ms (1.04x faster); parse/iterparse not significant.

Decision:

- Accept for validation. This is the intended StringZilla-style fast-rejection shape using portable `memchr()` rather than architecture-specific SIMD.

## Validation

- Focused tests:
  - `./python -m test test_xml_etree test_xml_etree_c -j1`: passed, 462 tests run, 12 skipped.
- Full suite:
  - `./python -m test -j4`: passed, 476 tests OK, 49,882 tests run, 2,596 skipped, 5 min 31 sec.
- Ecosystem / third-party:
  - pyperformance fast `xml_etree` A/B completed; compare output in `benchmarks/results/pyperformance-compare-e2.txt`.

## Acceptance Decision

- Decision: branch-local accept; ready for stacked validation.
- Accepted commit:
- Stacked winner commit:

## Notes

- Keep rejected ideas here too so the branch remains useful research.
