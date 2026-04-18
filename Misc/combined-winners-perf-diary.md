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
