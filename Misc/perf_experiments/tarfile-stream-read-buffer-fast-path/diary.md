        # tarfile stream read buffer fast path

        Branch: `exp-tarfile/stream-read-mainline`
        Base commit: `3263942ffef9ebb47facd3fe370443b06daa02bb`
        Manifest: `Misc/perf_experiments/tarfile-stream-read-buffer-fast-path/experiment.json`

        ## Goal

        Archetype: `common-case split` plus `allocator/accumulator refactor`.
        Tar stream reads still pay list-and-join churn in `_Stream._read()`
        even when `dbuf` already satisfies the request or one decompress step
        yields enough output.

        ## Targets

        - Lib/tarfile.py:538 _Stream._read

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - fresh stacked discovery report:
            - `Misc/perf_experiments/reports/stacked-discovery-candidates-2026-04-25.md`
          - collapsed input:
            - `/tmp/stacked-discovery-2026-04-24-refresh-inproc.txt`
          - relevant fresh leaf signal:
            - `Lib/tarfile.py:_Stream._read:556`
              about `102` samples (`0.39%`)
            - neighboring rejected family:
              - `Lib/compression/_common/_streams.py:DecompressReader.read:103`
                about `320` samples (`1.24%`)
        - Usage scan:
          - `_Stream._read()` handles compressed stream modes:
            - `r|gz`
            - `r|bz2`
            - `r|xz`
            - `r|zst`
            - plus `r|*` auto-detection through `_StreamProxy`
          - uncompressed `r|` is out of scope because it dispatches to
            `_Stream.__read()` instead of `_Stream._read()`
          - hot structural shape in `_Stream._read()`:
            - `self.dbuf` may already satisfy the request
            - otherwise one `self.cmp.decompress(...)` step often yields
              enough bytes
            - current implementation still allocates a list and joins even on
              those common one-step paths
        - Initial benchmark corpus:
          - `benchmarks/bench_tarfile_stream_read.py`
          - cases:
            - `T1_gz_stream_member_small_reads`
            - `T2_bz2_stream_member_small_reads`
            - `T3_xz_stream_member_small_reads`
            - `T4_gz_stream_member_large_reads`
            - `T5_bz2_stream_member_large_reads`
            - `T6_xz_stream_member_large_reads`
            - `T7_gz_stream_headers_only`
            - `T8_bz2_direct_small_reads`
            - `T9_xz_direct_small_reads`
        - Guardrails:
          - `guardrails/check_tarfile_stream_semantics.py`
          - target result:
            - `tarfile stream semantics: ok`

        ## Candidate Ledger

        ### E1

        Status: rejected at source proof.

        Thesis:

        - split the compressed `_Stream._read()` common path in two:
          return immediately when `dbuf` already has enough bytes, or when the
          first decompress step yields enough bytes; keep the old multi-step
          accumulation path as fallback

        Result:

        - guardrail:
          - `check_tarfile_stream_semantics.py`: passed
        - runtime proof:
          - `T1_gz_stream_member_small_reads`: `+3.09%`
          - `T2_bz2_stream_member_small_reads`: `+0.68%`
          - `T3_xz_stream_member_small_reads`: `+1.71%`
          - `T4_gz_stream_member_large_reads`: `+4.53%`
          - `T5_bz2_stream_member_large_reads`: `-0.99%`
          - `T6_xz_stream_member_large_reads`: `+3.92%`
          - `T7_gz_stream_headers_only`: `+3.27%`
          - `T8_bz2_direct_small_reads`: `+1.92%`
          - `T9_xz_direct_small_reads`: `+6.90%`
          - geomean: about `+2.76%`
        - clean source proof:
          - `T1_gz_stream_member_small_reads`: `+0.65%`
          - `T2_bz2_stream_member_small_reads`: `+0.53%`
          - `T3_xz_stream_member_small_reads`: `+1.78%`
          - `T4_gz_stream_member_large_reads`: `+0.27%`
          - `T5_bz2_stream_member_large_reads`: `-0.85%`
          - `T6_xz_stream_member_large_reads`: `+1.72%`
          - `T7_gz_stream_headers_only`: `+0.12%`
          - `T8_bz2_direct_small_reads`: `+2.98%`
          - `T9_xz_direct_small_reads`: `+5.66%`
          - geomean: about `+1.41%`

        Decision:

        - Rejected before focused validation. The common-case split is real,
          but once it moved from runtime monkeypatch to clean source proof the
          win collapsed below the promotion bar.

        ### E2

        Status: rejected at runtime proof.

        Thesis:

        - refine `E1` by avoiding the `dbuf + chunk` copy when `dbuf` is empty
          and the first decompress step already yields enough output

        Result:

        - runtime proof:
          - `T1_gz_stream_member_small_reads`: `+2.21%`
          - `T2_bz2_stream_member_small_reads`: `-0.64%`
          - `T3_xz_stream_member_small_reads`: `-1.11%`
          - `T4_gz_stream_member_large_reads`: `+6.31%`
          - `T5_bz2_stream_member_large_reads`: `-0.66%`
          - `T6_xz_stream_member_large_reads`: `+2.22%`
          - `T7_gz_stream_headers_only`: `+0.76%`
          - `T8_bz2_direct_small_reads`: `+2.05%`
          - `T9_xz_direct_small_reads`: `+5.99%`
          - geomean: about `+1.87%`

        Decision:

        - Rejected before source proof. The refinement did not improve on `E1`
          and weakened the mixed result.

        ## Validation

        - Focused tests:
        - Full suite:
        - Ecosystem / third-party:

        ## Acceptance Decision

        - Decision: rejected
        - Accepted commit:
        - Stacked winner commit:

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Current phase: `rejected`
