        # compression decompress reader read fast path

        Branch: `exp-compression/decompress-reader-mainline`
        Base commit: `3263942ffef9ebb47facd3fe370443b06daa02bb`
        Manifest: `Misc/perf_experiments/compression-decompress-reader-read-fast-path/experiment.json`

        ## Goal

        Archetype: `common-case split` plus `allocator/accumulator refactor`.
        Fresh stacked discovery still shows the shared decompression read loop as
        a real pure-Python cluster after the earlier winners. `bz2` and `lzma`
        both funnel through `compression._common._streams.DecompressReader.read()`,
        which still pays loop and repeated-state overhead even when one
        refill/decompress step yields output immediately.

        ## Targets

        - Lib/compression/_common/_streams.py:63 DecompressReader.read

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - fresh stacked discovery report:
            - `/tmp/stacked-discovery-2026-04-24-refresh-inproc.md`
          - collapsed input:
            - `/tmp/stacked-discovery-2026-04-24-refresh-inproc.txt`
          - relevant fresh leaf signal:
            - `Lib/compression/_common/_streams.py:DecompressReader.read:103`
              about `320` samples (`1.24%`)
            - `Lib/tarfile.py:_Stream._read:556`
              about `102` samples (`0.39%`)
            - `Lib/bz2.py:BZ2File.close:109`
              about `108` samples (`0.42%`)
        - Usage scan:
          - `Lib/bz2.py:BZ2File.__init__` wraps
            `_streams.DecompressReader(..., BZ2Decompressor, ...)`
            in `io.BufferedReader`
          - `Lib/lzma.py:LZMAFile.__init__` wraps
            `_streams.DecompressReader(..., LZMADecompressor, ...)`
            in `io.BufferedReader`
          - `Lib/gzip.py` is explicitly out of scope for this family because
            `_GzipReader` overrides `read()` with gzip-member-specific logic
          - `Lib/tarfile.py:_Stream._read()` has a structurally similar
            list-and-join loop, but it is a separate tarfile family unless the
            shared `compression._common` work proves too weak on its own
          - common hot shape in `DecompressReader.read()`:
            - not `size < 0`
            - not `_eof`
            - not `self._decompressor.eof`
            - one `read(BUFFER_SIZE)` / `decompress(..., size)` call already
              yields output
        - Initial benchmark corpus:
          - `benchmarks/bench_decompress_reader_read.py`
          - cases:
            - `C1_bz2_raw_chunked`
            - `C2_lzma_raw_chunked`
            - `C3_bz2_raw_multistream`
            - `C4_lzma_raw_multistream`
            - `C5_bz2_file_chunked`
            - `C6_lzma_file_chunked`
            - `C7_bz2_file_readall`
            - `C8_lzma_file_readall`
        - Guardrails:
          - `guardrails/check_decompress_reader_semantics.py`
          - target result:
            - `decompress reader semantics: ok`

        ## Candidate Ledger

        ### E1

        Status: rejected at runtime proof.

        Thesis:

        - split the dominant non-EOF path out of
          `DecompressReader.read()`: if the current decompressor is active,
          perform one direct refill/decompress attempt and return immediately
          when that first call yields bytes; fall back to the original loop only
          when the first attempt produces no output

        Result:

        - guardrail:
          - `check_decompress_reader_semantics.py`: passed
        - runtime proof:
          - `C1_bz2_raw_chunked`: `-17.72%`
          - `C2_lzma_raw_chunked`: `-27.32%`
          - `C3_bz2_raw_multistream`: `-18.16%`
          - `C4_lzma_raw_multistream`: `-18.99%`
          - `C5_bz2_file_chunked`: `-12.86%`
          - `C6_lzma_file_chunked`: `-0.86%`
          - `C7_bz2_file_readall`: `-1.96%`
          - `C8_lzma_file_readall`: `-5.01%`
          - geomean: about `-13.31%`

        Decision:

        - Rejected before any clean source branch. The proposed fast path added
          enough extra Python branching that it lost badly even on the direct
          raw-reader cases it was supposed to help. This is not a “slightly
          noisy” miss; it is a structural no-go for this shape.

        ## Validation

        - Guardrails:
          - runtime guardrail: passed
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
