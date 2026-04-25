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
        - Guardrails:

        ## Candidate Ledger

        ### E1

        Status: pending.

        Thesis:

        - try an optimistic `mkdir(name, mode)` first for the simple leaf-create
          path, and only fall back to the current split/exists/recursive logic
          on missing-parent or already-exists/error cases so the common path
          stops paying unconditional `path.split()` / `path.exists()` setup

        Result:

        - pending

        Decision:

        - pending

        ## Validation

        - Focused tests:
        - Full suite:
        - Ecosystem / third-party:

        ## Acceptance Decision

        - Decision:
        - Accepted commit:
        - Stacked winner commit:

        ## Notes

        - Keep rejected ideas here too so the branch remains useful research.
        - Archetype: `common-case split`
        - Anti-pattern check: this is not being opened as a thin wrapper guess;
          the direct `mkdir` vs `makedirs` headroom check was run first.
        - Current phase: `usage-scan`
        - Next gate: build a focused harness and guardrail around
          existing-parent, missing-parent, trailing-slash, bytes-path, and
          `exist_ok` cases before any source patch exists.
