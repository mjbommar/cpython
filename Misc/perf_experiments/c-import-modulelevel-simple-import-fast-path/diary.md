        # C import module-level simple import fast path

        Branch: `exp-import/c-modulelevel-mainline`
        Base commit: `2d21eb5651e76845536b5c6385d6236dee32c0b1`
        Manifest: `Misc/perf_experiments/c-import-modulelevel-simple-import-fast-path/experiment.json`

        ## Goal

        Archetype: common-case split plus control-flow lifting. PyImport_ImportModuleLevelObject() still carries generic fromlist/dotted-name post-processing even after the dominant absolute no-fromlist no-dot import path has already produced the module. A narrow early return for that shape may reduce repeated import-statement overhead on both cache-hit and cached-submodule paths without changing import semantics.

        ## Targets

        - Python/import.c:PyImport_ImportModuleLevelObject
- Python/import.c:import_find_and_load

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - ranked from the current top-25 runtime review list:
            `Python/import.c:4174 PyImport_ImportModuleLevelObject`
            plus `Python/import.c:4098 import_find_and_load`
        - Usage scan:
          - direct source inspection:
            - `IMPORT_NAME` on plain `import math` reaches
              `PyImport_ImportModuleLevelObject(..., fromlist=NULL, level=0)`
            - builtin `__import__()` default reaches the same C entry point with
              an exact empty tuple `fromlist`
            - `_PyFunction_Vectorcall()` was rejected as the thin-wrapper
              anti-pattern before opening this family
          - AST census over `Lib/` excluding tests:
            - `2,302` `import` aliases total
            - `2,171` plain no-dot aliases (`94.31%`)
            - `131` dotted aliases (`5.69%`)
            - `1,695` `from ... import ...` nodes total
            - `1,202` absolute (`70.91%`)
            - `493` relative (`29.09%`)
        - Initial benchmark corpus:
          - `I1_plain_math`
          - `I2_plain_json`
          - `I3_dotted_email`
          - `I4_dotted_xml`
          - `I5_from_email`
          - `I6_from_xml`
          - `I7_builtin_default`
          - `I8_builtin_empty_tuple`
          - baseline means:
            - `I1`: `111.6 ns`
            - `I2`: `120.8 ns`
            - `I3`: `228.2 ns`
            - `I4`: `222.9 ns`
            - `I5`: `383.9 ns`
            - `I6`: `377.8 ns`
            - `I7`: `107.1 ns`
            - `I8`: `322.6 ns`
        - Guardrails:
          - `check_c_import_simple_semantics.py`
          - passed

        ## Candidate Ledger

        ### E1

        Status: pending.

        Thesis:

        - In `PyImport_ImportModuleLevelObject()`, once `mod` has been fetched
          or loaded, absolute imports with no `fromlist` and no dot in `name`
          can return `mod` immediately.
        - Keep the generic `PyObject_IsTrue(fromlist)` path for arbitrary
          `fromlist` objects; only special-case `NULL`, `None`, and exact empty
          tuples.

        Result:

        - clean source patch on
          `/home/mjbommar/projects/personal/cpython-import-c-modulelevel-mainline`
        - candidate:
          - early return in `PyImport_ImportModuleLevelObject()` for
            `level == 0` plus `fromlist is NULL/None/exact-empty-tuple` when
            `name` has no dot
        - same-worktree source A/B:
          - `I1_plain_math`: `+2.80%`
          - `I2_plain_json`: `-2.79%`
          - `I3_dotted_email`: `-2.08%`
          - `I4_dotted_xml`: `-2.55%`
          - `I5_from_email`: `+0.15%`
          - `I6_from_xml`: `+0.67%`
          - `I7_builtin_default`: `+0.75%`
          - `I8_builtin_empty_tuple`: `+2.44%`
          - geomean: `-0.10%`
        - clean source guardrail: passed

        Decision:

        - Reject.
        - The simple-import early return helps only the narrow plain-import
          shape and does not clear the mixed corpus gate once dotted-import
          controls are included.

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
        - The useful lesson is not just "no win": after the importlib and
          marshal winners, this layer of the C import spine is already thin
          enough that a small common-case split can easily lose back its gains
          on dotted-name controls.
