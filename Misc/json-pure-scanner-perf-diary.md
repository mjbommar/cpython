# JSON pure-scanner perf diary

Date: `2026-04-23`
Branch: `exp-json/pure-scanner-mainline`

## Goal

Evaluate the still-open pure-Python JSON scanner tracker item:

- `Lib/json/scanner.py:15` `py_make_scanner()` / nested `_scan_once`

This branch starts with a focused scanner harness rather than reusing
the decoder diary, so the next decision is driven by token-dispatch
costs in the fallback scanner itself.

## Harness

Added:

- `Misc/json-pure-scanner-perf-data/json_pure_scanner_bench.py`
- `Misc/json-pure-scanner-perf-data/guardrails.py`

The benchmark forces the pure-Python scanner path by constructing
`JSONDecoder` instances with `json.scanner.make_scanner` temporarily set
to `py_make_scanner`.

Scenarios:

- `S1_scan_constants`
- `S2_scan_numbers`
- `S3_scan_array`
- `S4_scan_object`
- `S5_decode_line`
- `S6_decode_nested`

Guardrails cover:

- direct `scan_once()` for literals, numbers, arrays, and objects
- full nested decode parity
- rejection of malformed literals and bare `-`

## Baseline profile

Constants profile (`true`, `false`, `null`, `NaN`, `Infinity`,
`-Infinity`, `50000` outer loops):

- `scanner.py:66 scan_once`: `0.134s`
- `scanner.py:29 _scan_once`: `0.126s`
- `re.Pattern.match`: `0.038s`
- `dict.clear`: `0.038s`

Numbers profile (`0`, `12345`, `-9999`, `12.5`, `-12.5e+2`,
`0.03125e-1`, `50000` outer loops):

- `scanner.py:29 _scan_once`: `0.296s`
- `scanner.py:66 scan_once`: `0.153s`
- `re.Pattern.match`: `0.147s`
- `re.Match.groups`: `0.058s`
- `re.Match.end`: `0.041s`

Nested decode profile (`2000` decodes):

- `decoder.py:137 JSONObject`: `0.656s`
- `scanner.py:29 _scan_once`: `0.272s`
- `re.Pattern.match`: `0.148s`
- `_json.scanstring`: `0.079s`

Interpretation:

- the constants path was still paying avoidable regex work for
  `NaN` / `Infinity` / `-Infinity`
- the scanner wrapper itself had measurable per-call overhead
- number parsing remained regex-dominated, so any numeric tweak needed
  to be careful not to slow common integer and negative-number paths

## Candidate search

Rejected candidate A:

- bound `memo.clear()` once
- switched literals to `startswith()`
- short-circuited non-number first characters before the regex
- moved `-Infinity` ahead of the regex

Result:

- `S1` improved a lot, but real paths regressed
- `S2 -10.7%`, `S5 -7.6%`
- rejected as too broad and too hostile to normal negative numbers

Accepted candidate C:

- bind `memo.clear()` once as `memo_clear`
- use `string.startswith(...)` for `null`, `true`, `false`, `NaN`,
  and `Infinity`
- skip the regex entirely for `NaN` and `Infinity`
- keep `-Infinity` after the regex so normal negative numbers do not
  pay a prefix-probe penalty
- for float/exponent matches, pass `parse_float()` the matched slice
  `string[idx:end]` instead of rebuilding it from `groups()`

## Results

Run 1 (`/tmp/json-pure-scanner-baseline.json` vs
`/tmp/json-pure-scanner-candidate-c.json`):

- `S1_scan_constants`: `0.241978s -> 0.218713s` (`+10.64%`)
- `S2_scan_numbers`: `0.567292s -> 0.557066s` (`+1.84%`)
- `S3_scan_array`: `0.325620s -> 0.323290s` (`+0.72%`)
- `S4_scan_object`: `0.318578s -> 0.312483s` (`+1.95%`)
- `S5_decode_line`: `1.593952s -> 1.617146s` (`-1.43%`)
- `S6_decode_nested`: `2.923215s -> 2.844990s` (`+2.75%`)
- geomean: about `+2.68%`

Run 2 (`/tmp/json-pure-scanner-baseline2.json` vs
`/tmp/json-pure-scanner-candidate2.json`):

- `S1_scan_constants`: `0.504648s -> 0.438792s` (`+15.01%`)
- `S2_scan_numbers`: `1.119836s -> 1.130824s` (`-0.97%`)
- `S3_scan_array`: `0.651172s -> 0.645472s` (`+0.88%`)
- `S4_scan_object`: `0.639325s -> 0.634040s` (`+0.83%`)
- `S5_decode_line`: `3.243681s -> 3.252770s` (`-0.28%`)
- `S6_decode_nested`: `5.727394s -> 5.637994s` (`+1.59%`)
- geomean: about `+2.70%`

Two-run average:

- `S1_scan_constants`: `+13.55%`
- `S2_scan_numbers`: `-0.05%`
- `S3_scan_array`: `+0.83%`
- `S4_scan_object`: `+1.20%`
- `S5_decode_line`: `-0.66%`
- `S6_decode_nested`: `+1.98%`
- average geomean: about `+2.70%`

## Post-patch profile

Constants profile after the accepted patch:

- `scanner.py:30 _scan_once`: `0.144s`
- `scanner.py:75 scan_once`: `0.125s`
- `str.startswith`: `0.044s`
- `dict.clear`: `0.026s`
- `re.Pattern.match`: `0.014s`

Compared to baseline, the constants path cuts regex calls from `150000`
to `50000` in this profile.

Numbers profile after the accepted patch:

- `scanner.py:30 _scan_once`: `0.296s`
- `re.Pattern.match`: `0.143s`
- `scanner.py:75 scan_once`: `0.141s`
- `re.Match.groups`: `0.058s`
- `re.Match.end`: `0.041s`

This stayed effectively flat overall, which is what we wanted after
rejecting the broader first attempt.

## Validation

- custom pure-scanner guardrails: passed before and after
- focused stdlib tests: `./python -m test test_json` passed
- full suite: `./python -m test -j0`
  - `49,882` tests run
  - `2,623` skipped
  - `SUCCESS` in `4 min 35 sec`

## Decision

Accepted.

What we learned:

- the pure-Python scanner does still have a small but real filing
  candidate, especially around special-constant dispatch
- the safe win is not “make the dispatch ladder more clever everywhere”;
  it is “remove the wasted regex work where the first byte already
  determines the token family”
- normal number parsing is sensitive: the first attempt proved that even
  a seemingly small extra `-Infinity` prefix probe on every negative
  number is enough to erase the win
