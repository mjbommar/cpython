# JSON pure-decoder perf diary

Date: `2026-04-23`
Branch: `exp-json/pure-decoder-mainline`

## Goal

Evaluate the still-open pure-Python JSON decoder tracker items:

- `Lib/json/scanner.py:15` `py_make_scanner()` / `_scan_once`
- `Lib/json/decoder.py:137` `JSONObject()`

This branch starts with the higher-confidence `JSONObject()` common case:
when `object_pairs_hook` is `None`, build the dict directly instead of
building a list of pairs and converting it afterward.

## Harness

Added:

- `Misc/json-pure-decoder-perf-data/json_pure_decoder_bench.py`
- `Misc/json-pure-decoder-perf-data/guardrails.py`

The benchmark forces the pure-Python scanner path by constructing
`JSONDecoder` instances with `json.scanner.make_scanner` temporarily set
to `py_make_scanner`.

Scenarios:

- `P1_decode_line`
- `P2_decode_nested`
- `P3_raw_decode_whitespace`
- `P4_object_direct_large`
- `P5_object_direct_duplicate`
- `P6_object_pairs_hook`

Guardrails cover:

- direct decode and `raw_decode`
- duplicate-key last-wins behavior
- `object_hook`, `object_pairs_hook`, and their priority rules
- direct `JSONObject()` calls
- trailing-comma and missing-colon error rejection

## Baseline profile

Hot-path profile for `5000` decodes of a `120`-key object on clean
branch state:

- `decoder.py:137 JSONObject`: `0.848s`
- `scanner.py:29 _scan_once`: `0.538s`
- `re.Pattern.match`: `0.427s`
- `dict.setdefault`: `0.106s`
- `_json.scanstring`: `0.094s`
- `list.append`: `0.061s`

Interpretation:

- `JSONObject()` is the dominant Python frame in this fallback path.
- The current implementation pays avoidable work in the no-hook common
  case: tuple creation, list append, and a final `dict(pairs)` pass.

## Candidate

Patch:

- in `Lib/json/decoder.py`, when `object_pairs_hook is None`, build the
  result dict directly during `JSONObject()` parsing instead of building
  a list of `(key, value)` pairs and converting it at the end
- preserve the existing list-of-pairs path unchanged for
  `object_pairs_hook`
- preserve `object_hook` application on the final dict

I also tried a second variant that split the hook and no-hook loops into
two duplicated loops to remove one per-key branch. It was effectively
flat versus the simpler direct-dict version and made the code worse, so
it was rejected.

## Results

Run 1 (`/tmp/json-pure-decoder-baseline.json` vs
`/tmp/json-pure-decoder-candidate.json`):

- `P1_decode_line`: `1.593779s -> 1.546319s` (`+3.07%`)
- `P2_decode_nested`: `2.830316s -> 2.626948s` (`+7.74%`)
- `P3_raw_decode_whitespace`: `1.557291s -> 1.489660s` (`+4.54%`)
- `P4_object_direct_large`: `9.176767s -> 9.016091s` (`+1.78%`)
- `P5_object_direct_duplicate`: `0.611951s -> 0.577026s` (`+6.05%`)
- `P6_object_pairs_hook`: `0.762464s -> 0.751159s` (`+1.51%`)
- geomean: about `+4.09%`

Run 2 (`/tmp/json-pure-decoder-baseline2.json` vs
`/tmp/json-pure-decoder-candidate2.json`):

- `P1_decode_line`: `1.612107s -> 1.565302s` (`+2.99%`)
- `P2_decode_nested`: `2.887198s -> 2.634624s` (`+9.59%`)
- `P3_raw_decode_whitespace`: `1.548010s -> 1.515308s` (`+2.16%`)
- `P4_object_direct_large`: `9.331117s -> 9.198586s` (`+1.44%`)
- `P5_object_direct_duplicate`: `0.613063s -> 0.582648s` (`+5.22%`)
- `P6_object_pairs_hook`: `0.762794s -> 0.766591s` (`-0.50%`)
- geomean: about `+3.43%`

Two-run average:

- `P1_decode_line`: `+3.03%`
- `P2_decode_nested`: `+8.67%`
- `P3_raw_decode_whitespace`: `+3.34%`
- `P4_object_direct_large`: `+1.61%`
- `P5_object_direct_duplicate`: `+5.63%`
- `P6_object_pairs_hook`: `+0.49%`
- average geomean: about `+3.76%`

## Post-patch profile

Same `5000`-decode large-object profile after the accepted patch:

- `decoder.py:137 JSONObject`: `0.755s`
- `scanner.py:29 _scan_once`: `0.518s`
- `re.Pattern.match`: `0.439s`
- `dict.setdefault`: `0.104s`
- `_json.scanstring`: `0.086s`

Notably, `list.append` disappears from the hot list in the common
no-hook path, and `JSONObject()` itself drops by about `11%` in
internal time.

## Validation

- custom pure-decoder guardrails: passed before and after
- focused stdlib tests: `./python -m test test_json` passed
- full suite: `./python -m test -j0`
  - `49,881` tests run
  - `2,623` skipped
  - `SUCCESS` in `4 min 31 sec`

## Decision

Accepted.

What we learned:

- the pure-Python JSON decoder still has worthwhile internal hot-path
  structure to simplify, even after the stronger C-backed JSON work
  elsewhere
- `JSONObject()` is a good filing candidate because the improvement is
  real, the semantics are easy to guard, and the patch stays entirely in
  stdlib Python code
- the next pure-decoder follow-up, if we continue, should move to
  `json.scanner.py_make_scanner()` / `_scan_once` token-prefix and
  whitespace handling rather than making `JSONObject()` more complex
