# `html.escape` fast-path experiment

Branch: `exp-html/escape-fastpath`

## Goal

Check whether `Lib/html.py:escape()` has a small, safe pure-Python
optimization worth filing after the larger `json`, logging, AST, ABC,
datetime, UUID, `_PyUnicode_JoinArray`, and call-setup branches.

The motivation came from the earlier profile pass on official and
service-style workloads:

- `django_template` spent visible time in `django.utils.html.escape`
  and stdlib `html.escape`
- Starlette debug rendering used `html.escape()` directly on filenames,
  function names, traceback text, and code lines
- Mako/Django-style template paths also showed `str.replace()` and
  related string escaping primitives repeatedly

Unlike the C-heavy branches, this one is intentionally narrow: can we
make the common "already safe string" case cheaper without breaking the
existing `str`-subclass and exception semantics?

## Usage inventory

`html_escape_usage_scan.py` walked `Lib/`, `Lib/test/`, and the local
third-party sample environment under `/tmp/perf-extra-pkgs`.

Highlights from `usage-scan.json`:

- total direct `html.escape(...)` call sites: `43`
- package concentration:
  - `stdlib`: `28`
  - `pygments`: `6`
  - `starlette`: `5`
  - `django`: `3`
  - `gunicorn`: `1`
- argument shapes:
  - `name`: `19`
  - `call`: `12`
  - `attr`: `5`
  - `const_str`: `4`
- `quote` usage:
  - default `quote=True`: `33`
  - explicit `quote=False`: `8`
  - explicit `quote=True`: `2`

That inventory suggested three real workload families:

1. exact-`str` values that are already safe and do not need escaping
2. mixed HTML-ish strings that do need escaping
3. `quote=False` paths from stdlib HTTP / directory-listing style code

It also highlighted one compatibility pitfall:

- current `html.escape()` returns a plain `str` for `str` subclasses,
  even when no characters need escaping
- therefore a no-op fast path must only return the original object for
  exact `str`, not subclasses

## Benchmark corpus

Micros:

- `M1_safe_short`
- `M2_safe_medium`
- `M3_amp_only`
- `M4_angles`
- `M5_quote_heavy`
- `M6_mixed_html`
- `M7_http_path_quote_false`
- `M8_bmp_safe`

Real wrappers:

- `R1_stdlib_http_server`
- `R2_stdlib_pydoc_lines`
- `R3_django_escape`
- `R4_django_template`
- `R5_starlette_error`
- `R6_gunicorn_error`
- `R7_pygments_options`

`R4_django_template` intentionally mirrors the official
`pyperformance` benchmark body shape: many mostly safe cell values going
through Django’s `|escape` filter. That workload ended up being the
most important real discriminator.

## Candidate patterns

I tested seven variants:

1. `C1`: exact-`str` no-op fast path, then fall back to the current
   chained `replace()` logic.
   Compiler-theory framing: split the dominant no-op control-flow edge
   out of the hot path while preserving the current replacement graph.
2. `C2`: split `quote=True` / `quote=False` paths, pre-scan the
   original string for special characters, and only run the needed
   `replace()` calls.
3. `C3`: same shape as `C2`, but using `find()` instead of `in`.
4. `C4`: `any(...)` pre-scan plus baseline logic.
5. `C5`: `str.translate()` tables plus regex no-op guards.
6. `C6`: regex substitution.
7. `C7`: single-pass slice/pieces builder.

This was deliberately broader than "just try one no-op guard":

- `C1`/`C2` represent control-flow specialization
- `C5`/`C6` are alternative automaton-style substitution strategies
- `C7` is the classic single-pass builder refactor

## Candidate results

Short sweep vs baseline:

- `C1`
  - best overall real-workload balance
  - huge safe-string wins: `M2 +69.3%`, `M8 +55.0%`
  - real wrappers: `R1 +2.4%`, `R4 +3.4%`
  - but still small regressions on escape-heavy wrappers:
    `R2 -8.5%`, `R3 -6.4%`, `R7 -1.3%`
- `C2`
  - stronger on some escaping-heavy micros:
    `M3 +20.7%`, `M4 +4.6%`, `M5 +5.0%`
  - but clearly worse on the wrapper corpus:
    `R1 -18.6%`, `R5 -1.6%`
- `C3`
  - mostly noise / slight loss overall
- `C4`
  - broad regression; `any(...)` overhead dominated
- `C5` / `C6`
  - `translate()` and regex were non-starters for the mixed / escaping
    cases that matter here
- `C7`
  - single-pass builder was much slower across the board

This reduced the branch to `C1` vs `C2`.

## Confirm results

Longer confirm run for `C1` vs baseline:

- `M1_safe_short`: `+23.3%`
- `M2_safe_medium`: `+69.6%`
- `M8_bmp_safe`: `+54.7%`
- `R1_stdlib_http_server`: `+2.5%`
- `R4_django_template`: `+5.6%`
- `R5_starlette_error`: `+0.4%`
- `R2_stdlib_pydoc_lines`: `-8.6%`
- `R3_django_escape`: `-5.0%`
- `R6_gunicorn_error`: `-4.0%`
- `R7_pygments_options`: `-1.7%`

Actual patched stdlib confirm (`stdlib_confirm.json`) vs baseline:

- `M1_safe_short`: `+30.1%`
- `M2_safe_medium`: `+72.2%`
- `M8_bmp_safe`: `+55.2%`
- `R1_stdlib_http_server`: `+4.4%`
- `R4_django_template`: `+5.2%`
- `R5_starlette_error`: `+0.6%`
- `R2_stdlib_pydoc_lines`: `-4.7%`
- `R3_django_escape`: `-2.9%`
- `R6_gunicorn_error`: `-0.5%`
- `R7_pygments_options`: `-2.9%`

Geometric mean on the branch-local corpus:

- `C1` short sweep: `+11.1%`
- `C2` short sweep: `+11.3%`
- actual patched stdlib confirm: `+13.4%`

Interpretation:

- The branch is **real**, but it is not a universal win.
- It strongly helps the safe/no-op case.
- It mildly hurts workloads that are dominated by actual escaping.
- The direct Django template benchmark body is on the good side of that
  divide, which is why this branch stayed viable after the confirm run.

## Recommended patch

Keep `C1` only:

- exact-`str` no-op fast path
- separate `quote=True` and `quote=False` guard conditions
- otherwise preserve the existing chained `replace()` implementation

That shape keeps the patch very small and avoids the broader wrapper
regressions from `C2`.

## Validation

Deterministic wrapper checks:

- `PYTHONPATH=/tmp/perf-extra-pkgs:/tmp/cpython-html-escape/Lib /tmp/cpython-main-bench/python Misc/html-escape-perf-data/html_escape_checks.py`

Stdlib tests:

- passed:
  - `test_html`
  - `test_httpservers`
  - `test_xmlrpc`
  - `test_profiling.test_heatmap`

Third-party validation:

- import smoke passed for:
  - `django`, `starlette`, `gunicorn`, `pygments`, `jinja2`, `fastapi`,
    `httpx`, `anyio`, `werkzeug`
- the branch-local checks exercised:
  - Django `escape()`
  - Starlette debug HTML/plaintext generation
  - Gunicorn error-page rendering
  - Pygments `HtmlFormatter` option escaping

One test caveat:

- `test_pydoc` fails under the cross-tree `PYTHONPATH` setup used here,
  but the failure is a path-detection artifact, not a functional
  `html.escape` regression.
- `pydoc.Doc._is_stdlib_module()` compares module paths against the
  interpreter build tree. With `/tmp/cpython-main-bench/python` running
  against `/tmp/cpython-html-escape/Lib`, stdlib modules look
  "non-stdlib" to `pydoc`.
- The same `test_pydoc` run passes against `/tmp/cpython-main-bench/Lib`
  with no branch changes.

## Conclusion

`html.escape` does have a small viable fast path, but it is narrower
than the higher-priority wins.

The exact-`str` no-op guard is:

- safe in the tested corpus
- helpful for safe-string-heavy template traffic
- mildly negative for escape-heavy wrapper workloads

Recommendation: keep this branch as a **low-priority pure-Python
follow-up**, below the stronger `json`, logging, AST, ABC, datetime,
UUID, `_PyUnicode_JoinArray`, and call-setup branches. If it is ever
filed, it should be justified explicitly by the safe/no-op template
workload story, not presented as a universal escaping speedup.
