# `_PyUnicode_JoinArray` fast-path experiment

Branch: `exp-unicode/joinarray-fastpaths`

## Goal

Check whether `Objects/unicodeobject.c:_PyUnicode_JoinArray()` has a
small, safe C-level optimization worth filing after the logging, AST,
ABC, datetime, UUID, and heapq experiments.

The motivating profile signal came from the service-style workload
passes on `perf-ideas`: `str.join` was a visible C-backed hot path in
Jinja2, Django template rendering, `prompt_toolkit`, and
`jsonschema`-style error formatting. `perf record` on the Jinja2 render
corpus also showed `_PyUnicode_JoinArray` directly in the sampled C
stack.

## Usage inventory

`unicode_join_usage_scan.py` walked `Lib/`, `Lib/test/`, and the local
third-party sample environment under `/tmp/perf-extra-pkgs`.

Highlights from `usage-scan.json`:

- `.join(...)` receiver shapes were concentrated in:
  - generic attribute receivers: `1999`
  - empty-string literals: `657`
  - `", "` literals: `539`
  - newline literals: `336`
  - single-space literals: `228`
- argument shapes were dominated by:
  - simple names: `2390`
  - attributes: `631`
  - calls: `572`
  - generator expressions: `479`
- top package clusters:
  - `django`: `491`
  - `pygments`: `198`
  - `celery`: `113`
  - `email`: `83`
  - `werkzeug`: `71`
  - `prompt_toolkit`: `63`

That gave two clear workload families to benchmark:

- empty-separator joins on exact Unicode sequences
- short ASCII-separator joins, especially `", "`, `"\n"`, and `" "`

## Benchmark corpus

Micros:

- `M1_ascii_empty_join`
- `M2_ascii_sep_join`
- `M3_bmp_empty_join`
- `M4_wide_sep_ascii_join`
- `M5_mixed_width_empty_join`
- `M6_small_n_join`

Real wrappers:

- `R1_jinja2_render`
- `R2_django_template_render`
- `R3_django_filter_join`
- `R4_prompt_toolkit_flush`
- `R5_jsonschema_error_strings`

The real workloads were intentionally chosen to keep the dependency
surface mostly pure-Python or stdlib-facing while still exercising
production-relevant join traffic.

## Candidate patterns

I tested six variants, each motivated by a specific specialization idea:

1. `C1`: replace `last_obj` with `last_kind` in the prepass so an empty
   separator no longer disables the memcpy path just because the empty
   string is ASCII.
2. `C2`: `C1` plus hoist the first item out of both copy loops.
   Compiler-theory framing: remove the `i != 0` control dependency from
   the loop body and make the hot recurrence monomorphic.
3. `C3`: `C1` plus explicit `seplen == 0` loop splits.
   Data-oriented framing: specialize the dominant empty-separator state.
4. `C4`: `C2` plus explicit `seplen == 0` loop splits.
5. `C5`: `C2` plus direct byte stores for ASCII separators of length
   `1` or `2` inside the memcpy path.
6. `C6`: `C5` plus dedicated `seqlen == 2/3` copy paths.

## Candidate results

Short sweep vs rebuilt baseline:

- `C1`
  - helped the right empty-separator cases (`M3 -3.9%`, `M5 -3.1%`)
  - but regressed / stayed noisy on real wrappers (`R3 +2.6%`,
    `R4 +0.1%`)
- `C2`
  - broadest consistent win
  - `M3 -34.5%`, `M5 -6.9%`
  - `R1 -4.5%`, `R2 -5.4%`, `R3 -7.6%`, `R4 -3.4%`, `R5 -8.7%`
- `C3`
  - helped the empty-join micros, but overfit them
  - `M2 +4.9%`, `M4 +8.0%`
- `C4`
  - mostly dominated by `C2`
  - still good on empty joins, but gave back too much on `M6` and the
    real wrappers
- `C5`
  - huge `", "` micro win (`M2 -19.6%`)
  - looked attractive at first, but the longer confirm run was less
    convincing on the broader real wrappers than `C2`
- `C6`
  - extra small-`N` logic did not justify itself
  - regressed `M5` in the short sweep and added complexity without a
    clearer ecosystem win

Longer confirm runs narrowed the recommendation to `C2` vs `C5`.

`C2` confirm vs rebuilt baseline:

- `M1_ascii_empty_join`: `-6.3%`
- `M2_ascii_sep_join`: `-2.5%`
- `M3_bmp_empty_join`: `-34.2%`
- `M5_mixed_width_empty_join`: `-3.3%`
- `R1_jinja2_render`: `-3.5%`
- `R2_django_template_render`: `-5.1%`
- `R3_django_filter_join`: `-5.5%`
- `R4_prompt_toolkit_flush`: `-2.9%`
- `R5_jsonschema_error_strings`: `-8.3%`

`C5` confirm vs rebuilt baseline:

- `M2_ascii_sep_join`: `-22.8%`
- `M3_bmp_empty_join`: `-34.1%`
- `M5_mixed_width_empty_join`: `-7.1%`
- `R1_jinja2_render`: `-2.8%`
- `R2_django_template_render`: `-4.5%`
- `R3_django_filter_join`: `-5.9%`
- `R4_prompt_toolkit_flush`: `-2.1%`
- `R5_jsonschema_error_strings`: `-7.6%`

Interpretation:

- `C5` clearly over-performs on the tiny ASCII-separator micro.
- `C2` is simpler and wins more consistently on the broader wrapper
  corpus that motivated the branch in the first place.

## Recommended patch

Keep `C2`:

- prepass on `last_kind` instead of `last_obj`
- do not let `seplen == 0` inherit the separator kind into the memcpy
  gate
- hoist the first element out of both copy loops so the steady-state
  path does not re-check `i != 0`

That patch is small, local to `_PyUnicode_JoinArray`, and stays within
the existing algorithm. It is a control-flow specialization, not a
semantic rewrite.

## Validation

Branch-local deterministic checks:

- `PYTHONPATH=/tmp/perf-extra-pkgs ./python Misc/unicode-join-perf-data/unicode_join_checks.py`

Stdlib tests:

- `./python -m test -j4 test_str test_string test_json test_email test_unicode_file test_unicode_file_functions test_unicode_identifiers test_unicodedata test_userstring`

Third-party validation:

- import smoke passed for:
  - `jinja2`, `django`, `prompt_toolkit`, `jsonschema`, `celery`,
    `fastapi`, `httpx`, `flask`, `werkzeug`, `uvicorn`, `anyio`
- runnable local suite:
  - `484` `jsonschema` tests passed with the external-suite checkout
    file excluded:
    `pytest -q /tmp/perf-extra-pkgs/jsonschema/tests --ignore=/tmp/perf-extra-pkgs/jsonschema/tests/test_jsonschema_test_suite.py`

No functional regressions were observed in the tested corpus, and this
branch did not uncover a concrete semantic edge case analogous to the
heapq `NaN` problem.

## Conclusion

`_PyUnicode_JoinArray` is a real, viable small C optimization target.

The best patch is not a separator-specific trick or a deep copy
refactor. It is the smaller control-flow cleanup: pick the right graph
invariant (`last_kind`), avoid letting empty-separator state poison the
memcpy decision, and take the first element out of the recurrence.

Recommendation: treat this as a plausible small PR candidate after the
higher-priority logging / AST / ABC / datetime work, with `C2` as the
branch to keep.
