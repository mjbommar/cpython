# pickle pure-Python load/read fast path

Branch: `exp-pickle/load-read-mainline`
Base commit: `5a37cb8a24363a730302031721baeb264aff1a49`
Manifest: `Misc/perf_experiments/pickle-pure-python-load-read-fast-path/experiment.json`

## Goal

Archetype: `common-case split` plus `allocator/accumulator care`. Fresh
stacked discovery shows pure-Python `pickle` load/read still hot after the old
save-side winner already living in the stacked branch. The smallest safe first
shape is to fast-path unframed small reads in `_Unframer.read()`, because most
opcode reads are tiny and currently still pay the `_chunked_file_read()`
helper.

## Targets

- `Lib/pickle.py:288 read`
- `Lib/pickle.py:314 _chunked_file_read`
- `Lib/pickle.py:1478 load`

## Success Criteria

- Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload
  reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked
  winner branch.

## Input Evidence

- Profiles:
  - `/tmp/stacked-discovery-2026-04-24.pstats`
  - stacked discovery attribution on the current stacked branch:
    - `Lib/pickle.py:1478 load`: about `9.656s` cumulative
    - `Lib/pickle.py:288 read`: about `4.001s`
    - `Lib/pickle.py:314 _chunked_file_read`: about `1.660s`
    - hot loader helpers still include:
      - `load_binunicode`: about `0.541s`
      - `load_short_binunicode`: about `0.460s`
      - `load_binint2`: about `0.687s`
      - `load_binint1`: about `0.200s`
- Usage scan:
  - this is fresh work, not a duplicate of the older pure-Python save-side
    exact-container winner already present on the stacked branch
  - the remaining pure-Python load cluster is concentrated in `_Unframer.read`
    and `_chunked_file_read`, not in public wrapper overhead
  - `_Unpickler.load()` already binds `read` and `dispatch` locally, so the
    first better bet is the read helper rather than the main dispatch loop
- Initial benchmark corpus:
  - `benchmarks/bench_pickle_pure_load_read.py`
  - cases:
    - `P1_load_small_list`
    - `P2_load_nested`
    - `P3_load_strings`
    - `P4_load_stream_multi`
    - `P5_load_large_bytes`
  - result artifacts:
    - `benchmarks/results/runtime-baseline.json`
    - `benchmarks/results/runtime-small-read-fast-path.json`
- Guardrails:
  - `guardrails/check_pickle_pure_load_read_semantics.py`
  - result: passed (`pickle pure load/read guardrails: ok`)

## Candidate Ledger

### E1

Status: rejected.

Thesis:

When the unpickler is not currently inside a frame and `n <= _MIN_READ_BUF_SIZE`,
return `self.file_read(n)` directly from `_Unframer.read()` and skip the
`_chunked_file_read()` helper call.

Result:

- Runtime proof only: about `+0.18%` geomean.
- Details:
  - `P1_load_small_list`: `-1.16%`
  - `P2_load_nested`: `-0.84%`
  - `P3_load_strings`: `-0.41%`
  - `P4_load_stream_multi`: `+1.90%`
  - `P5_load_large_bytes`: `+1.43%`

Decision:

Rejected as a source candidate. The mixed result is too weak for a clean branch.

### E2

Status: rejected.

Thesis:

Replace `_chunked_file_read()`'s repeated `b += chunk` growth with a chunk list
plus one `b''.join(chunks)` at the end.

Result:

- Runtime proof only: about `-0.34%` geomean.
- Details:
  - `P1_load_small_list`: `-2.05%`
  - `P2_load_nested`: `-0.07%`
  - `P3_load_strings`: `-1.10%`
  - `P4_load_stream_multi`: `-0.27%`
  - `P5_load_large_bytes`: `+0.14%`
  - `P6_load_huge_bytes`: `+1.48%`
  - `P7_chunked_read_2mb`: `-4.77%`
  - `P8_chunked_read_8mb`: `+4.11%`

Decision:

Rejected. It only helped the largest multi-chunk case and regressed the more
common two-chunk loads.

### E3

Status: rejected.

Thesis:

Replace `_chunked_file_read()` growth with a `bytearray` accumulator and one
final `bytes(buf)` conversion.

Result:

- Runtime proof only: about `-10.68%` geomean.
- Details:
  - `P5_load_large_bytes`: `-7.22%`
  - `P7_chunked_read_2mb`: `-48.27%`
  - `P8_chunked_read_8mb`: `-15.19%`

Decision:

Rejected immediately. This was materially worse across the chunked-read cases.

### E4

Status: rejected.

Thesis:

Use the original `_chunked_file_read()` up to 2 MiB and switch to the
`b''.join(chunks)` strategy only for larger multi-chunk reads.

Result:

- Runtime proof only: about `-0.08%` geomean.
- Details:
  - `P1_load_small_list`: `-2.30%`
  - `P2_load_nested`: `-1.16%`
  - `P3_load_strings`: `-4.92%`
  - `P4_load_stream_multi`: `-2.83%`
  - `P5_load_large_bytes`: `-1.39%`
  - `P6_load_huge_bytes`: `+1.62%`
  - `P7_chunked_read_2mb`: `+3.55%`
  - `P8_chunked_read_8mb`: `+7.34%`

Decision:

Rejected. The large-read wins were real, but they did not outweigh the
regressions on the ordinary load-heavy cases.

## Validation

- Guardrails:
  - runtime guardrail: passed
- Focused tests:
  - not run
- Full suite:
  - not run
- Ecosystem / third-party:
  - not run

## Acceptance Decision

- Decision: rejected
- Accepted commit:
- Stacked winner commit:

## Notes

- Current phase: `rejected`
- No candidate in this family cleared the source-branch gate.
- If this family is ever reopened, the next shape should likely target
  opcode-specific decode helpers or a larger architectural load path rather
  than more `_chunked_file_read()` micro-surgery.
