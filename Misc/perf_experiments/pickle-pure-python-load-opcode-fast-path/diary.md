        # pickle pure python load opcode fast path

        Branch: `exp-pickle/load-opcodes-mainline`
        Base commit: `faa7d29705c03f8ab5141a015128de52fe932f61`
        Manifest: `Misc/perf_experiments/pickle-pure-python-load-opcode-fast-path/experiment.json`

        ## Goal

        Archetype: `control-flow lifting` plus `common-case split`.
        After the rejected read-helper family, the remaining pure-Python load
        signal is concentrated in tiny opcode helpers like `load_binunicode`,
        `load_short_binunicode`, `load_binint1/2`, and tuple arity opcodes, so
        the next plausible shape is reducing per-opcode helper and stack
        mutation overhead rather than more file-read micro-surgery.

        ## Targets

        - Lib/pickle.py:1325 load
        - Lib/pickle.py:1500 load_binunicode
        - Lib/pickle.py:1568 load_short_binunicode
        - Lib/pickle.py:1422 load_binint1
        - Lib/pickle.py:1426 load_binint2
        - Lib/pickle.py:1582 load_tuple1
        - Lib/pickle.py:1586 load_tuple2
        - Lib/pickle.py:1590 load_tuple3

        ## Success Criteria

        - Guardrails pass before any performance claim is trusted.
- A focused harness shows a repeatable local win or a clear macro-workload reason to proceed.
- Focused stdlib tests pass before promotion.
- The full suite passes before the experiment is merged into the stacked winner branch.

        ## Input Evidence

        - Profiles:
          - inherited from the rejected read-helper family:
            - `Lib/pickle.py:1478 load`: about `9.656s` cumulative
            - helper leaves still called out there:
              - `load_binunicode`: about `0.541s`
              - `load_short_binunicode`: about `0.460s`
              - `load_binint2`: about `0.687s`
              - `load_binint1`: about `0.200s`
          - fresh stacked discovery report:
            - `Lib/pickle.py:_Unpickler.load:1580`
              about `201` leaf samples (`0.78%`)
        - Usage scan:
          - this family intentionally reopens the same subsystem at the point
            the rejected read-helper family said to reopen it: opcode-specific
            decode helpers instead of `_Unframer.read()` micro-surgery
          - opcode census on representative protocol 4/5 payloads showed the
            expected dominant shapes:
            - `BININT1`: `1246`
            - `SHORT_BINUNICODE`: `555`
            - `TUPLE3`: `200`
            - plus container scaffolding opcodes (`MEMOIZE`, `BINGET`,
              `MARK`, `SETITEMS`, `APPENDS`)
          - representative object slices:
            - string-heavy payloads are dominated by `SHORT_BINUNICODE`
            - tuple-heavy payloads are dominated by `TUPLE3` and `BININT1`
            - nested dict/list payloads are dominated by `BININT1`, `BINGET`,
              `EMPTY_DICT`, `SETITEMS`, and `APPENDS`
        - Initial benchmark corpus:
          - next gate: build a focused load harness that isolates:
            - unicode-heavy payloads
            - small-int-heavy payloads
            - tuple-arity-heavy payloads
            - mixed nested container payloads
        - Guardrails:
          - next gate: reuse the prior pickle load guardrail first, then widen
            only if the prototype changes stack/memo semantics

        ## Candidate Ledger

        ### E1

        Status: pending.

        Thesis:

        -

        Result:

        -

        Decision:

        -

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
        - Current phase: `usage-scan`
        - Next gate: focused harness plus baseline artifacts before any
          runtime monkeypatch candidate exists.
