## Combined winners stack

Branch: `exp-combined/winners-stack`

Goal: combine the strongest validated experiment branches into one build,
measure the integrated effect against rebuilt `main`, and check whether
the wins stack cleanly enough to justify a broader prototype branch.

### Included branches

- `marshal-safe-cycle-design`
  - kept the self-reference fix commit only
- `exp-pickle/4-pure-python-exact-containers`
- `exp-logging/hot-path`
- `exp-ast/nodevisitor-cache`
- `exp-json/research`
- `exp-isinstance/type-lookup`
- `exp-datetime/fromisoformat-fastpath`
- `exp-uuid/c-fastpath`
- `exp-unicode/joinarray-fastpaths`
- `exp-ceval/initialize-locals-fastpath`
- `exp-importlib/file-dir-cache-mainline`
- `exp-contextlib/doc-skip-mainline`

### Deliberately excluded

- `exp-attr/generic-getattr-fastpaths`
  - correctness regressions
- `exp-asyncio/eventloop-hotpaths`
  - weak result
- `exp-logging/c-helpers`
  - larger maintenance surface than the Python-only logging branch
- `exp-heapq/asyncio-tuple-compare`
  - known `NaN` edge-case risk

### Benchmark panel

Compared:

- baseline: rebuilt `main` at `d61fcf834d1`
- combined: rebuilt `exp-combined/winners-stack`

Panel:

- logging realistic bench
- json realistic bench
- ast `NodeVisitor` bench
- `fromisoformat` bench
- unicode join bench
- `initialize_locals` bench
- pure-Python pickle bench
- `uuid4` / `uuid7` microbench

Overall result:

- geometric mean across all collected metrics: `10.1%` faster

Per-group geometric means:

- logging: `9.2%` faster
- json: `11.0%` faster
- ast: `20.5%` faster
- pickle: `17.6%` faster
- uuid: `20.3%` faster
- fromisoformat: `0.4%` faster
- unicode join: `0.4%` faster
- initialize_locals: `0.2%` faster

Notable integrated results:

- logging still lands strongly:
  - `R1_quiet_request -12.0%`
  - `R2_verbose_request -11.5%`
  - `R4_access_log_only -11.1%`
- json still lands strongly:
  - `J2_log_line_dumps -16.3%`
  - `J4_bulk_dump_100k -13.8%`
  - `J8_deep_tree_roundtrip -11.5%`
- ast keeps the largest broad single-family win:
  - `M1_dispatch_miss_flat -31.4%`
  - `R2_pygettext -20.2%`
  - `R6_black_magicfinder -15.6%`
- pickle remains strong on dump-heavy pure-Python paths:
  - `deep_list.dump -49.1%`
  - `list_of_ints_10k.dump -35.2%`
  - `nested_list_of_dicts.dump -34.4%`
- uuid stays compelling:
  - `uuid4 -36.3%`
  - `uuid7` essentially flat

### What did not stack cleanly

The branch-local winners do not add linearly.

- `fromisoformat` stayed roughly flat overall, with a mix of small wins
  and small regressions once layered into the larger stack.
- `_PyUnicode_JoinArray` lost most of its standalone branch advantage in
  this combined build. The integrated result was roughly flat overall.
- `initialize_locals` also compressed to roughly flat overall in this
  panel.

That does not mean those branches were bad. It means the integrated
prototype is now dominated by the larger wins from `json`, `logging`,
`ast`, `pickle`, and `uuid`, and some smaller effects disappear into
noise or interact with adjacent call/string-path changes.

### Recommendation

Keep this branch as an integration prototype, not as a PR candidate.

- It is useful for validating that the strongest branch-local wins
  compose to a real end-to-end gain.
- It shows that the combined stack still clears a meaningful broad-panel
  bar at about `10%`.
- It also shows that some smaller wins are not independently visible
  once the larger changes are in place, so branch-level filing
  decisions should still be made per family rather than by this
  aggregate branch alone.

## 2026-04-22 update: importlib `FileFinder` cache split

Accepted and cherry-picked commit:

- `45dc9000986` / `d7572b84494`
  `perf: cache FileFinder file and directory entries`

Validation:

- clean-mainline branch `exp-importlib/file-dir-cache-mainline` passed
  `./python -m test -q -j8`: `49,882` tests, `491/502` files,
  `SUCCESS` in `4 min 19 sec`
- stacked branch passed focused import tests after the cherry-pick:
  `test_importlib`, `test_import`, `test_zipimport`, `test_pkgutil`,
  and `test_runpy`

Stacked import panel result
(`baseline-e3-guardrails.json` vs `stacked-after-importlib-e3.json`):

- `I1_top_level_source`: `-4.33%`
- `I2_top_level_pyc`: `-10.44%`
- `I3_package_child_source`: `-4.93%`
- `I4_package_child_pyc`: `-5.23%`
- `I5_loaded_hit_top_level`: `+2.37%`
- `I6_find_spec_package_child`: `-5.28%`
- `I7_find_spec_missing_cold`: `-14.00%`
- `I8_find_spec_missing_warm`: `-21.33%`
- geometric mean: about `-8.15%`

What we learned:

- the importlib candidate stacks well in the integration branch, even
  though the clean-mainline package-child scenarios were noisier
- the biggest durable wins come from repeated `find_spec` and
  missing-module paths, where avoiding positive-hit restats and repeated
  mode checks matters
- already-loaded imports do not benefit, as expected, because they
  return before `FileFinder`

## 2026-04-22 update: contextlib doc assignment skip

Accepted and cherry-picked commit:

- `51a31b86447` / `fd70137e444`
  `perf: skip redundant contextmanager doc assignment`

Validation:

- clean-mainline branch `exp-contextlib/doc-skip-mainline` passed
  `./python -m test -q -j8`: `49,882` tests, `491/502` files,
  `SUCCESS` in `4 min 15 sec`
- stacked branch passed focused contextlib/doc tests after the
  cherry-pick: `test_contextlib`, `test_pydoc`, and `test_inspect`

Contextlib panel result
(`mainline-baseline-docskip.json` vs `mainline-docskip.json`):

- `C1_simple_with`: `-8.69%`
- `C2_with_value`: `-8.13%`
- `C3_swallow_value_error`: `-4.37%`
- `C4_context_decorator`: `-5.88%`
- `C5_docstring_cm`: `-1.22%`
- geometric mean: about `-5.70%`

What we learned:

- the earlier contextlib local-binding ideas were noise; the accepted
  win comes from avoiding one redundant instance-dict write per no-doc
  `@contextmanager` construction
- `cm.__doc__` remains the same through class lookup for no-doc
  context managers, while custom function docstrings are still assigned
  onto the instance
- the only observable behavioral difference is that no-doc context
  manager instances no longer carry a redundant `__doc__` key in
  `cm.__dict__`
