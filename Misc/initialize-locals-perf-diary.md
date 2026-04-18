# `initialize_locals` / call-setup experiment

Branch: `exp-ceval/initialize-locals-fastpath`

## Goal

Check whether the call-setup family around:

- `Python/ceval.c:1674` `initialize_locals`
- `Python/ceval.c:1977` `_PyEvalFramePushAndInit`
- `Python/ceval.c:2082` `_PyEval_Vector`

has a narrow, service-relevant optimization that is worth pursuing
without turning into an undirected “optimize ceval” project.

## Why this branch

The service-style profiling runs had already shown the family as
genuinely hot:

- `_PyEval_EvalFrameDefault`: about `28%` of sampled user-space time in
  the combined wrapper probe
- `_PyEval_Vector`: about `2.32%`
- `initialize_locals`: about `1.46%`
- `_PyEvalFramePushAndInit`: about `0.96%`
- `PyObject_Vectorcall`: about `1.07%`

That is broad enough to matter, but still narrow enough to attack at
the call-entry helpers rather than the opcode loop itself.

## Usage inventory

`initialize_locals_usage_scan.py` scanned `Lib/` and the local
third-party sample environment under `/tmp/perf-extra-pkgs`.

The key signal was consistent across stdlib and third-party code:

- calls with **no keywords** dominate
  - stdlib: `372,792` zero-keyword calls vs `30,385` keyworded
  - third party: `119,020` zero-keyword calls vs `14,554` keyworded
- “simple positional” calls dominate
  - stdlib: `370,188` simple positional vs `32,989` everything else
  - third party: `116,329` simple positional vs `17,245` everything else
- the dominant positional buckets are `1`, `2`, and `0`
- function signatures are overwhelmingly simple
  - stdlib: `66,426` simple signatures vs `3,325` richer ones
  - third party: `29,948` simple signatures vs `3,802` richer ones

This justified two design principles:

1. prioritize the no-keyword path
2. pay attention to `0-4` positional args rather than only the
   worst-case generic loops

## Benchmark corpus

Micros:

- `M1_exact_positional`
- `M2_defaults_fill`
- `M3_keyword_call`
- `M4_varargs_call`
- `M5_bound_method`
- `M6_closure_call`
- `M7_many9_call`

Real wrappers:

- `R1_jinja2_render`
- `R2_django_template`
- `R3_jsonschema_validate`
- `R4_celery_eager`

This split was deliberate:

- the micros isolate call-shape effects that should move
  `initialize_locals`
- the real wrappers tell us whether those wins survive in codebases
  where the call path is mixed with a lot of ordinary Python work

## Candidate patterns

I tested eight variants:

1. `C1`: replace the positional local copy loop with `memcpy`
2. `C2`: `C1` plus exact no-keyword / no-varargs / no-varkw / no-kwonly
   early return
3. `C3`: `C2` plus trailing-defaults early return
4. `C4`: split the no-keyword path into a dedicated helper, with bulk
   positional copy and the same downstream logic
5. `C5`: `C4` plus exact-signature early return inside the no-keyword
   helper
6. `C6`: `C4` plus `0-4` positional manual copy switch in the no-keyword
   helper
7. `C7`: `C6` plus the same `0-4` small-copy switch in `_PyEval_Vector`
   for no-keyword calls
8. `C8`: `C7` plus small-copy switching in the generic keyword-capable
   positional copy path as well

## Candidate results

Short sweep vs rebuilt baseline:

- `C1`
  - good direct-call movement, but mixed on real wrappers
  - `M1 -5.6%`, `M2 -3.3%`, `R1 -4.5%`
  - `R2 +2.5%`, `R3 +1.3%`
- `C2`
  - exact positional fast path was too narrow
  - `M1 -5.0%`, but `M2 +2.6%`, `R2 +2.7%`, `R3 +1.8%`
- `C3`
  - widening the early-return set made things worse almost everywhere
  - effectively a reject
- `C4`
  - first broadly promising patch
  - `M1 -4.6%`, `M2 -1.6%`, `M3 -10.1%`, `M4 -5.2%`
  - `R1 -5.4%`, `R3 -2.2%`, `R4 -0.6%`
  - `R2` roughly flat
- `C5`
  - exact fast path inside the split helper was not a clear improvement
- `C6`
  - small-copy switch in the no-keyword helper helped most micros and
    wrappers
  - still left enough uncertainty that a confirmatory pass was worth it
- `C7`
  - strongest overall pre-confirm result once `_PyEval_Vector` got the
    same `0-4` small-copy treatment
- `C8`
  - adding small-copy switching to the generic keyword-capable path
    looked attractive in the short sweep, but the longer comparison made
    it the runner-up rather than the winner

## Confirm runs and recommendation

The final decision came down to `C7` vs `C8`.

`C7` confirm vs rebuilt baseline:

- `M1_exact_positional`: `-6.6%`
- `M2_defaults_fill`: `-4.7%`
- `M3_keyword_call`: `-9.6%`
- `M5_bound_method`: `-2.7%`
- `M6_closure_call`: `-3.4%`
- `M7_many9_call`: `-4.5%`
- `R1_jinja2_render`: `-6.5%`
- `R2_django_template`: `+0.5%`
- `R3_jsonschema_validate`: `-2.2%`
- `R4_celery_eager`: `-2.1%`

`C8` confirm vs rebuilt baseline:

- `M1_exact_positional`: `-5.5%`
- `M2_defaults_fill`: `-2.6%`
- `M3_keyword_call`: `-8.6%`
- `M4_varargs_call`: `-4.7%`
- `M6_closure_call`: `+1.8%`
- `R1_jinja2_render`: `-4.7%`
- `R2_django_template`: `+0.9%`
- `R3_jsonschema_validate`: `-0.4%`
- `R4_celery_eager`: `-3.3%`

Interpretation:

- `C8` spreads the small-copy idea more aggressively, but the extra
  generic-path logic gives back too much on closure-heavy and
  `jsonschema`-like traffic.
- `C7` is the better compromise:
  - dedicated no-keyword helper path
  - `0-4` small-copy switch inside that helper
  - matching `0-4` small-copy switch in `_PyEval_Vector` for
    no-keyword calls

That patch is still small enough to reason about and is materially
better than the baseline across most of the tested corpus.

## Validation

Branch-local checks:

- `PYTHONPATH=/tmp/perf-extra-pkgs ./python Misc/initialize-locals-perf-data/initialize_locals_checks.py`

Stdlib tests:

- `./python -m test -j4 test_call test_extcall test_positional_only_arg test_keywordonlyarg test_inspect test_functools test_generators test_decorators test_compile`

Third-party validation:

- import smoke passed for:
  - `jinja2`, `django`, `jsonschema`, `celery`, `fastapi`, `httpx`,
    `anyio`, `flask`, `werkzeug`, `uvicorn`
- runnable local suite:
  - `484` `jsonschema` tests passed with the external-suite checkout
    file excluded

No functional regressions were observed in the tested corpus.

## Conclusion

This family is worth keeping on the board.

The right shape is **not** “more and more early returns in
`initialize_locals`”. The successful pattern is:

- split the hot no-keyword path into its own control-flow graph
- specialize the common `0-4` positional case
- mirror that shape in `_PyEval_Vector` so the temporary argument
  materialization path matches the locals-init fast path

Recommendation: keep `C7` as a plausible next-step branch result. It is
broader than the earlier module-local micros, but still scoped enough to
discuss as a targeted call-setup optimization rather than a generic
interpreter-loop patch.
