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
          - `benchmarks/bench_pickle_pure_load_opcodes.py`
          - cases:
            - `P1_load_unicode_list`
            - `P2_load_small_int_list`
            - `P3_load_tuple3_list`
            - `P4_load_nested_mixed`
            - `P5_load_stream_multi`
        - Guardrails:
          - `guardrails/check_pickle_pure_load_opcode_semantics.py`
          - target result:
            - `pickle pure load opcode guardrails: ok`

        ## Candidate Ledger

        ### E1

        Status: rejected at runtime proof.

        Thesis:

        - inline the dominant small load opcodes directly inside
          `_Unpickler.load()` for protocol-4/5-heavy traffic:
          `BININT1`, `BININT2`, `SHORT_BINUNICODE`, tuple arity opcodes,
          `MEMOIZE`, `BINGET`, `MARK`, `APPENDS`, `SETITEMS`, and a few empty
          container literals, while falling back to the normal dispatch table
          for everything else

        Result:

        - guardrail passed:
          - `pickle pure load opcode guardrails: ok`
        - focused runtime proof on the stacked interpreter was strongly
          negative:
          - `P1_load_unicode_list`: `-31.55%`
          - `P2_load_small_int_list`: `+1.23%`
          - `P3_load_tuple3_list`: `-18.17%`
          - `P4_load_nested_mixed`: `-32.39%`
          - `P5_load_stream_multi`: `-29.69%`
          - geomean: about `-23.07%`
        - artifacts:
          - `benchmarks/results/runtime-baseline.json`
          - `benchmarks/results/runtime-candidate-e1.json`

        Decision:

        - reject the family before any clean source branch
        - the Python-level mega-dispatch shape loses badly on unicode-heavy,
          tuple-heavy, nested, and stream-multi traffic, so there is no reason
          to spend a clean proof branch on it

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
        - Next gate: none
        - The family matched the intended archetype on paper, but the
          implementation crossed into the `manual Python-level control-flow
          blowup` failure mode: too much inline interpreter work in one loop
          overwhelmed any helper-call savings.
