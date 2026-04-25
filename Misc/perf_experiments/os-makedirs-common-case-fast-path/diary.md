        # os makedirs common case fast path

        Branch: `exp-os/makedirs-mainline`
        Base commit: `23a03177997723b721c02e53b58d3fd03ac42267`
        Manifest: `Misc/perf_experiments/os-makedirs-common-case-fast-path/experiment.json`

        ## Goal

        Common-case split: for the dominant leaf-create case where the parent already exists and the caller uses ordinary string paths with default mode, os.makedirs() likely spends reviewable Python time in split/exists/recursive setup before the final mkdir syscall, so an optimistic direct-mkdir-first shape may recover that overhead while preserving the current fallback semantics.

        ## Targets

        - Lib/os.py:222 makedirs

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - stacked discovery refresh report:
            - group `Lib/os.py`: about `157` leaf samples (`0.61%`)
            - leaf `Lib/os.py:makedirs`: about `129` samples (`0.50%`)
        - Usage scan:
          - direct stdlib and tooling callsites are broad and mostly simple:
            - rough scan found `64` default simple callsites and `18`
              `exist_ok=True` callsites with extra args in `Lib/` and `Tools/`
            - representative non-test callers include:
              - `Lib/tarfile.py`
              - `Lib/shutil.py`
              - `Lib/py_compile.py`
              - `Lib/trace.py`
              - `Lib/zipfile/__init__.py`
              - `Lib/venv/__init__.py`
              - `Lib/test/libregrtest/main.py`
          - direct headroom check for the leaf-create common case
            (`parent exists`, default mode, `exist_ok=False`) showed real
            Python overhead:
            - `os.mkdir()` best: about `5980.5 ns`
            - `os.makedirs()` best: about `10098.9 ns`
            - ratio: about `0.59x`
        - Initial benchmark corpus:
          - `benchmarks/bench_os_makedirs.py`
          - cases:
            - `M1_leaf_default`
            - `M2_leaf_exist_ok_missing`
            - `M3_nested_default`
            - `M4_bytes_leaf_default`
            - `M5_existing_dir_exist_ok`
        - Guardrails:
          - `guardrails/check_os_makedirs_semantics.py`
          - target result:
            - `os makedirs semantics: ok`

        ## Candidate Ledger

        ### E1

        Status: accepted and stacked.

        Thesis:

        - try an optimistic `mkdir(name, mode)` first for the simple leaf-create
          path, and only fall back to the current split/exists/recursive logic
          on missing-parent or already-exists/error cases so the common path
          stops paying unconditional `path.split()` / `path.exists()` setup

        Result:

        - guardrail passed:
          - `os makedirs semantics: ok`
        - focused runtime proof with the helper monkeypatch:
          - `M1_leaf_default`: `+37.20%`
          - `M2_leaf_exist_ok_missing`: `+37.31%`
          - `M3_nested_default`: `-7.13%`
          - `M4_bytes_leaf_default`: `+35.88%`
          - `M5_existing_dir_exist_ok`: `+36.52%`
          - geomean: about `+26.55%`
          - artifacts:
            - `benchmarks/results/runtime-baseline.json`
            - `benchmarks/results/runtime-candidate-e1.json`
        - clean source proof on `exp-os/makedirs-mainline`:
          - `M1_leaf_default`: `+30.89%`
          - `M2_leaf_exist_ok_missing`: `+30.02%`
          - `M3_nested_default`: `-7.94%`
          - `M4_bytes_leaf_default`: `+39.72%`
          - `M5_existing_dir_exist_ok`: `+29.53%`
          - geomean: about `+23.17%`
          - artifacts:
            - `benchmarks/results/source-baseline-a.json`
            - `benchmarks/results/source-candidate-e1-a.json`

        Decision:

        - accept
        - the optimistic `mkdir()` first split materially speeds the real
          dominant leaf-create cases, keeps bytes and `exist_ok=True` common
          traffic fast, and the nested-chain regression is small enough to
          survive source proof and full validation

        ## Validation

        - Focused tests:
          - clean branch:
            - `test_os test_pathlib test_shutil test_tarfile test_zipfile test_py_compile`
            - `SUCCESS` in `19.6 sec`
          - stacked branch:
            - `test_os test_pathlib test_shutil test_tarfile test_zipfile test_py_compile`
            - `SUCCESS` in `19.7 sec`
        - Full suite:
          - clean branch:
            - `49,882` run, `2,620` skipped, `SUCCESS` in `4 min 15 sec`
          - stacked branch:
            - `49,892` run, `2,620` skipped, `SUCCESS` in `4 min 14 sec`
        - Ecosystem / third-party:

        ## Acceptance Decision

        - Decision: stacked
        - Accepted commit: `7c59b8539f2`
        - Stacked winner commit: `521c5363fb8`

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Archetype: `common-case split`
        - Anti-pattern check: this is not being opened as a thin wrapper guess;
          the direct `mkdir` vs `makedirs` headroom check was run first.
        - Current phase: `stacked`
        - Next gate: none
        - Because `os` is frozen in this build, the clean source proof required
          a real out-of-tree build and could not be faked with a `PYTHONPATH`
          override against the main interpreter.
