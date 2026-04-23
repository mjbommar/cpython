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

## 2026-04-22 update: zipfile `PyZipFile.writepy()` validation

Accepted stacked commits:

- `be36223f1d0` / `711d9312b69`
  `perf: speed up PyZipFile package traversal`
- `e2fa4ef914a`
  `perf: preserve PyZipFile dot-py edge case`

Validation:

- clean-mainline branch `exp-zipfile/writepy-mainline` passed
  `./python -m test -q test_zipfile`: `379` tests, `3` skipped,
  `SUCCESS` in `18.0 sec`
- clean-mainline branch `exp-zipfile/writepy-mainline` passed
  `./python -m test -q -j8`: `49,882` tests, `491/502` files,
  `SUCCESS` in `4 min 16 sec`
- stacked branch passed focused `test_zipfile` after the semantic guard
  follow-up: `379` tests, `3` skipped, `SUCCESS` in `18.3 sec`

Clean-mainline zipfile panel result
(`/tmp/zipfile-clean-main-baseline-final.json` vs
`/tmp/zipfile-clean-main-candidate-final.json`):

- `Z1_flat_package_tiny`: `-6.07%`
- `Z2_nested_package_tiny`: `-3.44%`
- `Z3_nested_package_filtered_even`: `-7.89%`
- `Z4_plain_directory_tiny`: `+0.17%`
- `Z5_single_large_module`: `+4.08%`
- geometric mean: about `-2.73%`

What we learned:

- the durable win is recursive package traversal, where `os.scandir()`
  avoids repeated path joins and directory stats
- non-package directory traversal should stay on the original simpler
  path because the broader `scandir()` rewrite was noisier and less
  consistently helpful
- replacing `splitext(filename)[1] == ".py"` with
  `filename.endswith(".py")` needs an explicit `filename != ".py"`
  guard to preserve the historical leading-dot filename behavior

## 2026-04-22 update: importlib `SourceLoader.get_code()`

Accepted and cherry-picked commit:

- `c154e3f1238` / `befb979dcf6`
  `perf: delay bytecode memoryview creation`

Validation:

- clean-mainline branch `exp-importlib/get-code-mainline` passed
  focused import tests: `test_importlib`, `test_import`, and
  `test_zipimport`
- clean-mainline branch passed `./python -m test -q -j8`:
  `49,882` tests, `491/502` files, `SUCCESS` in `4 min 18 sec`
- stacked branch passed the same focused import tests after the
  cherry-pick

Direct `get_code()` panel result
(`/tmp/get-code-baseline-r3-main.json` vs
`/tmp/get-code-candidate-e2-r2.json`):

- `G1_timestamp_pyc_hit`: `-5.93%`
- `G2_unchecked_hash_pyc_hit`: `-4.53%`

## 2026-04-23 update: concurrent interpreters queue reload blocker

Accepted and cherry-picked commit:

- `374a801488f` / `d4de12c4641`
  `concurrent: preserve queue UNBOUND across reload`

Why this is in the stack:

- this is a correctness fix, not a throughput win
- it fixes a real baseline bug around
  `concurrent.interpreters.create_queue` aliases surviving
  `importlib.reload(concurrent.interpreters._queues)`
- that bug was also blocking clean validation for newer importlib-family work

Validation:

- clean blocker branch `fix-concurrent/queues-reload-unbound` passed
  `./python -m test -j4`: `49,882` run, `2,625` skipped,
  `SUCCESS` in `5 min 32 sec`
- stacked branch passed focused concurrent/import regression slices after the
  cherry-pick:
  `test_concurrent_futures.test_interpreter_pool`,
  `test_interpreters`,
  `test_struct`,
  `test_httpservers`,
  and `test_profiling`

What we learned:

- the earlier reduced-order `test_struct` failure was a real baseline bug, not
  an importlib regression
- the fix is small enough to stand as an independent winner and should sit
  underneath later importlib-family promotions

## 2026-04-23 update: importlib `_call_with_frames_removed()` fast path

Accepted and cherry-picked commit:

- `f861e6c4766` / `62601d5f522`
  `importlib: fast-path _call_with_frames_removed`

Validation:

- clean importlib branch
  `exp-importlib/call-with-frames-removed-mainline` passed
  focused import tests plus `./python -m test -j4`:
  `49,882` run, `2,623` skipped, `SUCCESS` in `5 min 31 sec`
- stacked branch passed focused import/concurrent regression slices after the
  cherry-pick:
  `test_importlib`, `test_import`, `test_zipimport`, `test_runpy`,
  `test_concurrent_futures.test_interpreter_pool`, `test_interpreters`,
  `test_struct`, `test_httpservers`, and `test_profiling`
- stacked branch then passed `./python -m test -j4`:
  `49,892` run, `2,622` skipped, `SUCCESS` in `5 min 32 sec`

Focused importlib result:

- Python callable, no kwargs: `223.6 ns -> 181.1 ns`
- builtin callable, no kwargs: `171.8 ns -> 136.8 ns`
- tiny Python-module import: `94,382.9 ns -> 88,356.3 ns`

What we learned:

- `_call_with_frames_removed()` was paying avoidable
  `CALL_FUNCTION_EX` / empty-kwargs overhead on the common path
- the no-kwargs split is reviewable, semantics-safe, and broad enough to matter
  across import-heavy flows
- the family only became promotable after separating the unrelated concurrent
  interpreters blocker into its own accepted fix

## 2026-04-23 update: pure-Python JSON `JSONObject()` direct-dict path

Accepted and cherry-picked commit:

- `82e23d571c7` / `5a988a0db2a`
  `perf: speed up pure Python JSON object decode`

Validation:

- clean-mainline branch `exp-json/pure-decoder-mainline` passed
  `./python -m test test_json`: `226` tests, `3` skipped,
  `SUCCESS` in `4.1 sec`
- clean-mainline branch passed `./python -m test -j0`:
  `49,881` tests run, `2,623` skipped, `SUCCESS` in `4 min 31 sec`
- stacked branch passed `./python -m test test_json`:
  `226` tests, `3` skipped, `SUCCESS` in `4.1 sec`
- stacked branch passed `./python -m test -j0`:
  `49,892` tests run, `2,621` skipped, `SUCCESS` in `4 min 33 sec`

Clean-mainline pure-decoder panel result
(`json-pure-decoder-baseline*.json` vs `json-pure-decoder-candidate*.json`,
two-run average):

- `P1_decode_line`: `+3.03%`
- `P2_decode_nested`: `+8.67%`
- `P3_raw_decode_whitespace`: `+3.34%`
- `P4_object_direct_large`: `+1.61%`
- `P5_object_direct_duplicate`: `+5.63%`
- `P6_object_pairs_hook`: `+0.49%`
- geometric mean: about `+3.76%`

What we learned:

- the pure-Python JSON fallback still has a worthwhile internal hot path
  even after the larger C-backed JSON work
- the winning simplification is narrow and semantics-preserving:
  `JSONObject()` now constructs the result dict directly in the common
  `object_pairs_hook is None` case instead of building a list of pairs
  and converting it with `dict(pairs)` at the end
- a more aggressive split-loop rewrite was tested and rejected because
  it did not beat the simpler version enough to justify the added code
  complexity

## 2026-04-23 update: pure-Python JSON scanner literal fast path

Accepted and cherry-picked commit:

- `38baaf19aea` / `dc800fc1ecb`
  `perf: speed up pure Python JSON scanner`

Validation:

- clean-mainline branch `exp-json/pure-scanner-mainline` passed
  `./python -m test test_json`: `226` tests, `3` skipped,
  `SUCCESS` in `4.1 sec`
- clean-mainline branch passed `./python -m test -j0`:
  `49,882` tests run, `2,623` skipped, `SUCCESS` in `4 min 35 sec`
- stacked branch passed `./python -m test test_json`:
  `226` tests, `3` skipped, `SUCCESS` in `4.1 sec`
- stacked branch passed `./python -m test -j0`:
  `49,892` tests run, `2,621` skipped, `SUCCESS` in `4 min 33 sec`

Clean-mainline pure-scanner panel result
(`json-pure-scanner-baseline*.json` vs `json-pure-scanner-candidate*.json`,
two-run average):

- `S1_scan_constants`: `+13.55%`
- `S2_scan_numbers`: `-0.05%`
- `S3_scan_array`: `+0.83%`
- `S4_scan_object`: `+1.20%`
- `S5_decode_line`: `-0.66%`
- `S6_decode_nested`: `+1.98%`
- geometric mean: about `+2.70%`

What we learned:

- the durable scanner win is in removing wasted regex work for special
  constants, not in making the whole dispatch ladder more aggressive
- the accepted patch binds `memo.clear()` once, uses `startswith()` for
  the literal probes, skips the regex for `NaN` and `Infinity`, keeps
  `-Infinity` after the regex so normal negative numbers stay flat, and
  passes the matched slice directly to `parse_float()`
- a broader first attempt that also short-circuited more token families
  before the regex was rejected because it regressed normal
  negative-number and line-decode paths
- `G3_checked_hash_pyc_hit`: `-3.92%`
- `G4_source_compile_no_write`: `+0.82%`
- `G5_stale_timestamp_pyc`: `-2.13%`
- `G6_bad_magic_pyc`: `-1.37%`
- geometric mean: about `-2.87%`

What we learned:

- the accepted patch is intentionally tiny: delay
  `memoryview(data)[16:]` until after pyc validation succeeds
- a broader lazy-exception-details rewrite was rejected because it
  changed private helper signatures and measured slightly slower overall
- most remaining `get_code()` cost is real work: filesystem reads,
  `marshal.loads`, source hashing, and `compile()`

## 2026-04-22 update: asyncio `Handle._run()` arity fast path

Accepted and cherry-picked commit:

- `4a4bbfb2c6e` / `47b2a77f184`
  `perf: specialize asyncio Handle callback arity`

Validation:

- clean-mainline branch `exp-asyncio/handle-run-mainline` passed full
  `test_asyncio`: `2,708` tests, `SUCCESS` in `1 min 31 sec`
- clean-mainline branch passed `./python -m test -q -j8`:
  `49,882` tests, `491/502` files, `SUCCESS` in `4 min 19 sec`
- stacked branch passed full `test_asyncio` after the cherry-pick:
  `2,708` tests, `SUCCESS` in `1 min 31 sec`

Final asyncio handle panel result
(`/tmp/asyncio-handle-baseline-v2.json` vs
`/tmp/asyncio-handle-candidate-e5.json`):

- `A1_direct_noargs`: `-35.22%`
- `A2_direct_onearg`: `-29.30%`
- `A3_direct_twoargs`: `-18.95%`
- `A4_direct_mixed_70_20_10`: `-29.93%`
- `A5_run_once_ready_noargs`: `-12.47%`
- `A6_run_once_ready_onearg`: `-9.79%`
- `A7_run_once_ready_mixed_70_20_10`: `-12.57%`
- geometric mean: about `-21.75%`

What we learned:

- avoiding `*args` expansion in `Handle._run()` is a large direct win,
  but only if common arities are handled together
- a no-args-only branch regressed one-arg callbacks; the accepted shape
  handles 0, 1, and 2 args before falling back to the original star call
- local bindings in this method must be explicitly cleared to preserve
  asyncio task/future refcycle behavior

## 2026-04-22 update: pathlib `PurePath.relative_to()`

Accepted and cherry-picked commit:

- `7f4aae53207` / `c3cfbeb4a07`
  `perf: fast path PurePath.relative_to prefixes`

Validation:

- clean-mainline branch `exp-pathlib/relative-to-mainline` passed
  `test_pathlib test_zipfile`: `1,752` tests, `SUCCESS` in `19.9 sec`
- clean-mainline branch passed `./python -m test -q -j8`:
  `49,882` tests, `491/502` files, `SUCCESS` in `4 min 14 sec`
- stacked branch passed `test_pathlib test_zipfile` after the
  cherry-pick

Current pathlib panel result
(`/tmp/pathlib-relative-baseline-current.json` vs
`/tmp/pathlib-relative-candidate-current.json`):

- `M1_posix_direct_prefix`: `-82.32%`
- `M2_posix_string_prefix`: `-72.37%`
- `M3_posix_walk_up`: `-1.77%`
- `M4_posix_negative`: `-91.02%`
- `M5_windows_direct_prefix_casefold`: `-60.44%`
- `M6_windows_walk_up_casefold`: `-0.63%`
- `R1_cpython_repo_positive`: `-74.70%`
- `R2_cpython_repo_string_positive`: `-66.35%`
- `R3_cpython_repo_walk_up`: `-2.23%`
- geometric mean: about `-62.66%`

What we learned:

- the non-`walk_up` exact-type prefix case can avoid constructing and
  comparing parent path objects entirely
- the fast path must exclude subclasses that override equality
- current `-j8` full-suite validation removed the older sequential
  full-suite ambiguity around unrelated local failures

## 2026-04-22 update: stacked-suite correctness cleanup

The stacked winner branch initially failed the full suite in three places:

- `test_descr`
- `test_marshal`
- `test_threading`

Focused reruns confirmed these were deterministic stack failures, not
flaky test noise.

Accepted cleanups:

- removed the unsafe `PyType_IsSubtype()` and `find_name_in_mro()` prototype
  shortcuts from the `isinstance/type-lookup` experiment
- changed marshal tuple handling so legal indirect tuple self-references
  remain accepted, while incomplete tuples are rejected only at hash-based
  insertion sites (`dict` keys and `set`/`frozenset` members)
- fixed the logging hot-path experiment to cache only the main-thread ident,
  not the `threading.main_thread()` object itself

Validation:

- `./python -m test -q test_descr`: `SUCCESS`
- `./python -m test -q test_marshal`: `SUCCESS`
- `./python -m test -q test_descr test_marshal test_threading test_logging`:
  `765` tests, `17` skipped, `SUCCESS` in `33.0 sec`
- `./python -m test -q -j8`: `49,892` tests, `2,620` skipped,
  `491/502` test files, `SUCCESS` in `4 min 13 sec`

What we learned:

- subtype and MRO lookup fast paths are high-risk unless they preserve custom
  MRO behavior exactly; the current shortcut shape is rejected for the stack
- marshal cannot globally delay tuple reference registration because existing
  version-3+ data depends on list/dict values being able to point back to the
  tuple under construction
- the narrow marshal hazard is hash-based insertion of an incomplete tuple,
  so the guard belongs at dict-key and set-member insertion sites
- module-level caches in stdlib hot paths must not retain lifecycle-sensitive
  objects such as `threading.Thread` instances across `fork()`

## 2026-04-22 update: importlib `_find_and_load()` loaded-module fast path

Accepted and cherry-picked commit:

- `fe49f1cb16a` / `3572c122f67`
  `perf: fast path already-loaded imports`

Clean-mainline result
(`/tmp/importlib-find-load-baseline.json` vs
`/tmp/importlib-find-load-candidate-e2.json`):

- `loaded_builtin`: `249 ns` -> `184 ns`, `1.35x faster`
- `loaded_python`: `244 ns` -> `183 ns`, `1.34x faster`
- reload and missing-module cases: no significant change
- pyperf significant geometric mean: about `1.10x faster`

Validation:

- clean-mainline focused import tests:
  `test_importlib test_import test_zipimport`, `1,477` tests,
  `31` skipped, `SUCCESS` in `9.9 sec`
- clean-mainline full suite:
  `49,881` tests, `2,624` skipped, `491/502` test files,
  `SUCCESS` in `4 min 15 sec`
- stacked focused import tests:
  `1,477` tests, `31` skipped, `SUCCESS` in `9.3 sec`
- stacked full suite:
  `49,892` tests, `2,620` skipped, `491/502` test files,
  `SUCCESS` in `4 min 13 sec`

What we learned:

- already-loaded imports are cheap but high-volume enough that shaving the
  lock/spec path is still measurable
- the fast return is only safe for exact module objects whose `__spec__` is
  `None` or exact `ModuleSpec`; custom specs must stay on the original path
  because reading `_initializing` may execute Python and mutate `sys.modules`
- `_bootstrap.py` cannot reference injected `sys` at module import time, so
  the exact module type cache must be initialized in `_setup()`

## 2026-04-23 update: pathlib glob `_StringGlobber.scandir()` tuple fast path

Accepted and cherry-picked commit:

- `a447c868d00` / `a0a9f825350`
  `perf: speed up pathlib glob scandir tuples`

Clean-mainline result
(`baseline3` / `candidate5`, `baseline4` / `candidate6`):

- `G1_flat_star`: about `+1.32%`
- `G2_flat_py`: about `+1.98%`
- `G3_tree_py_recursive`: about `+3.75%`
- `G4_tree_literal`: about `+0.80%`
- `G5_deep_target_recursive`: about `+5.72%`
- exact-patch two-run average geomean: about `+2.70%`

Validation:

- clean-mainline guardrails: passed
- clean-mainline focused tests:
  `test_glob test_pathlib`, `1,395` tests, `407` skipped,
  `SUCCESS` in `1.8 sec`
- clean-mainline full suite:
  `49,882` tests, `2,624` skipped, `491/502` test files,
  `SUCCESS` in `4 min 31 sec`
- stacked focused tests:
  `test_glob test_pathlib`, `1,395` tests, `407` skipped,
  `SUCCESS` in `1.8 sec`
- stacked full suite:
  `49,892` tests, `2,620` skipped, `491/502` test files,
  `SUCCESS` in `4 min 29 sec`

What we learned:

- the original `glob` microbench was pointed at the wrong code; the full-suite
  tracker item was really `pathlib` consuming `Lib/glob.py`, not public
  `glob.glob()`
- once retargeted to `Path.glob()` / `Path.rglob()`, the hotspot was
  `_StringGlobber.scandir()`, `select_wildcard()`, and
  `select_recursive_step()`, not selector construction itself
- changing the entry contract for `_GlobberBase` was too invasive because
  `_PathGlobber` and `zipfile.Path` still rely on the historical
  `(entry, name, path)` shape
- the winning patch is therefore intentionally small: preserve the contract,
  but materialize the tuple list directly inside the `os.scandir()` context
  instead of `list(scandir_it)` plus a generator expression

## 2026-04-23 update: exact `_pickle` dump/load hook fast path

Accepted and cherry-picked commit:

- `a469fc615e6` / `089b1d72a88`
  `perf: speed up exact _pickle dump and load hooks`

Clean-mainline result:

- exact-type two-run average:
  - `P1_dump_none_exact`: `+117.09%`
  - `P2_dump_small_list_exact`: `+64.99%`
  - `P3_dump_nested_exact`: `+7.18%`
  - `P4_load_none_exact`: `+18.10%`
  - `P5_load_small_list_exact`: `+6.53%`
  - `P6_load_nested_exact`: `-1.03%`
  - geometric mean: `+29.79%`
- broader mixed-stream exact benchmark:
  - `B1_dump_stream_mixed_exact`: `+91.61%`
  - `B2_load_stream_mixed_exact`: `+3.56%`
  - `B3_roundtrip_stream_mixed_exact`: `+33.65%`
  - geometric mean: `+38.42%`

Validation:

- clean-mainline guardrails: passed
- clean-mainline focused tests:
  `test_pickle test_picklebuffer test_copy test_copyreg test_shelve
  test_multiprocessing_spawn`, `2,047` tests, `129` skipped,
  `SUCCESS` in `1 min 33 sec`
- clean-mainline full suite:
  `49,882` tests, `2,603` skipped, `491/502` test files,
  `SUCCESS` in `4 min 32 sec`
- stacked focused tests:
  same 9-file bundle, `2,047` tests, `129` skipped,
  `SUCCESS` in `1 min 31 sec`
- stacked full suite:
  `49,892` tests, `2,600` skipped, `491/502` test files,
  `SUCCESS` in `4 min 29 sec`

What we learned:

- the top-25 `_pickle` wrapper lines were actionable, not just a proxy for
  deeper container work: exact built-in `Pickler.dump()` and
  `Unpickler.load()` were still paying measurable hook-resolution overhead
- the winning shape is exact-type specialization, not broader control-flow
  surgery: exact built-in `Pickler` skips `persistent_id` and
  `reducer_override` lookup work when there is no override, and exact
  built-in `Unpickler` skips `persistent_load` lookup work until a
  persistent-id opcode actually appears
- subclass and explicit instance-override semantics stay on the original path;
  guardrails covered both exact-instance hook override and subclass override
- the first baseline taken against a separately built binary overstated the
  result; the accepted numbers came only from stricter same-worktree revert /
  rebuild / benchmark / reapply / rebuild / benchmark cycles

## 2026-04-23 update: runpy `_run_code()` globals setup

Accepted and cherry-picked commit:

- `396e682fb51` / `3714f215cf2`
  `runpy: speed up _run_code globals setup`

Clean-mainline focused result:

- direct `_run_code()` common path:
  `680.5 ns -> 596.8 ns` (`+14.02%`)
- direct `_run_code()` with `init_globals`:
  `894.7 ns -> 711.8 ns` (`+25.70%`)
- direct `_run_code()` script path:
  `648.0 ns -> 572.8 ns` (`+13.13%`)
- `run_module()` tiny source module:
  `52,471.2 ns -> 49,136.0 ns` (`+6.79%`)
- `run_module(..., alter_sys=True)`:
  `58,443.0 ns -> 53,765.2 ns` (`+8.70%`)
- `run_module()` tiny package `__main__`:
  `56,411.3 ns -> 53,912.4 ns` (`+4.64%`)
- focused-harness geomean: about `+11.96%`

Validation:

- clean-mainline guardrail:
  `check_runpy_namespace_semantics.py` passed
- clean-mainline focused tests:
  `test_runpy`, `test_cmd_line`, `test_multiprocessing_main_handling`,
  `test_pdb`: `SUCCESS`
- clean-mainline full suite:
  `49,882` tests, `2,623` skipped, `491/502` test files,
  `SUCCESS` in `4 min 21 sec`
- stacked focused tests:
  `test_runpy test_profile`, and
  `test_cmd_line test_multiprocessing_main_handling test_pdb test_profiling`:
  `SUCCESS`
- stacked full suite:
  `49,892` tests, `2,621` skipped, `491/502` test files,
  `SUCCESS` in `4 min 24 sec`

What we learned:

- `runpy._run_code()` was still paying measurable overhead for the common
  namespace setup path even though the operation is just six fixed globals
- the smaller direct-assignment rewrite was better than the more specialized
  branchy prototype as a first real patch: it kept the surface area tiny and
  still preserved most of the measured win
- this is a good example of the funnel working correctly: the profile found a
  real pure-Python hotspot, the prototype harness proved it, the clean branch
  validated it, and the stacked branch accepted it without needing broader
  subsystem surgery

## 2026-04-23 update: subprocess POSIX-spawn setup fast path

Accepted and cherry-picked commit:

- `e01e5d63ae5` / `cc33c5b9547`
  `perf: speed up subprocess posix spawn setup`

Clean-mainline focused result:

- `S1_posix_spawn_common`:
  `0.046706s -> 0.025491s` (`+83.22%`)
- `S2_posix_spawn_pipe_actions`:
  `0.117136s -> 0.110570s` (`+5.94%`)
- `S3_execute_child_common_str`:
  `0.044770s -> 0.034505s` (`+29.75%`)
- `S4_execute_child_common_bytes`:
  `0.044604s -> 0.044669s` (`-0.15%`)
- focused-harness geomean: about `+25.93%`

Validation:

- clean-mainline guardrails:
  `guardrails.py` passed
- clean-mainline focused tests:
  `test_subprocess test_multiprocessing_spawn test_multiprocessing_fork
  test_multiprocessing_forkserver test.test_asyncio.test_subprocess`:
  `1,794` tests, `244` skipped, `SUCCESS` in `5 min`
- clean-mainline full suite:
  `49,882` tests, `2,623` skipped, `491/502` test files,
  `SUCCESS` in `4 min 20 sec`
- stacked focused tests:
  `test_subprocess test.test_asyncio.test_subprocess`:
  `442` tests, `45` skipped, `SUCCESS` in `1 min 21 sec`
- stacked focused tests:
  `test_multiprocessing_spawn test_multiprocessing_fork
  test_multiprocessing_forkserver`:
  `1,352` tests, `199` skipped, `SUCCESS` in `1 min 22 sec`
- stacked guardrails:
  `guardrails.py` passed
- stacked full suite:
  `49,892` tests, `2,620` skipped, `491/502` test files,
  `SUCCESS` in `4 min 18 sec`

What we learned:

- the broad regrtest profile signal around `popen_fork.py:Popen._launch` was
  actionable: the common POSIX-spawn path still had measurable Python-side
  setup overhead in `_posix_spawn()`, `_close_pipe_fds()`, and the executable
  directory gate in `_execute_child()`
- the winning shape is a bundle of very small common-path tightenings, not a
  semantic rewrite: cache the restore-signals `setsigdef` list once, skip the
  empty `_close_pipe_fds()` cleanup case, and avoid `os.path.dirname()` for
  exact `str` / `bytes` executables
- the bytes executable case is flat rather than meaningfully positive, but the
  full family still wins comfortably because the common POSIX-spawn and exact
  `str` paths dominate the measured panel
- the interrupted cherry-pick turned out to be an empty replay of an already
  stacked commit, so the real remaining work was validation and control-plane
  cleanup, not another code promotion
