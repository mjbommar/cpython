# AST `NodeVisitor.visit()` — experiment diary

Branch: `exp-ast/nodevisitor-cache`, off `main` at `cecf564073f`.

## Goal

Evaluate whether `Lib/ast.py:NodeVisitor.visit()` can be made cheaper
without breaking the large ecosystem of tools that subclass
`ast.NodeVisitor`.

## Process

1. Inventory stdlib users and a third-party sample that directly or
   indirectly subclass `ast.NodeVisitor`.
2. Define a small set of candidate `visit()` refactors.
3. Benchmark each variant against synthetic dispatch loops and real
   stdlib / third-party visitors.
4. Synthesize the recommendation and feed the result back into
   `Misc/cpython-perf-ideas.md`.

## Candidate refactors

- **Baseline** — current `method = 'visit_' + node.__class__.__name__`
  plus `getattr(self, method, self.generic_visit)` on every call.
- **Name cache** — cache only the method-name string per AST node type.
- **Instance cache** — cache the resolved bound visitor method per
  visitor instance and AST node type.
- **Class cache** — cache the resolved method on the visitor class via
  MRO lookup, avoiding the dynamic `getattr()` fast path entirely.

## Benchmark plan

Synthetic:

- dispatch-only, no-op generic fallback
- dispatch-only, hit-heavy visitor with common `visit_*` methods
- recursive generic visitor over a real CPython AST corpus

Real workloads:

- stdlib `_ast_unparse.Unparser`
- stdlib `Tools/i18n/pygettext.GettextVisitor`
- third-party `pycln.utils.scan.SourceAnalyzer`
- third-party `pyupgrade._plugins.legacy.Visitor`
- third-party `typeshed_client.parser._NameExtractor`
- third-party `black.handle_ipynb_magics.{MagicFinder, CellMagicFinder}`

## Ecosystem inventory targets

Stdlib:

- `Lib/_ast_unparse.py`
- `Lib/pyclbr.py`
- `Tools/i18n/pygettext.py`
- `Lib/test/test_ast/test_ast.py`
- `Lib/test/test_pyclbr.py`
- `Lib/test/test_tools/test_i18n.py`

Third-party sample environment:

- `black`
- `pyupgrade`
- `pycln`
- `typeshed_client`
- `vulture`
- `pydoctor`
- `pyanalyze`
- `ast_decompiler`

## Ecosystem inventory findings

`nodevisitor_usage_scan.py` found direct or local-derived
`ast.NodeVisitor` subclasses in:

- stdlib / tools: `Lib/_ast_unparse.py`, `Lib/pyclbr.py`,
  `Tools/i18n/pygettext.py`, `Tools/clinic/libclinic/dsl_parser.py`,
  and `Lib/test/test_ast/test_ast.py`
- third-party sample: `black`, `pycln`, `pyupgrade`,
  `typeshed_client`, `pydoctor`, `pyanalyze`, `vulture`,
  `ast_decompiler`

Top direct-subclass counts in the installed sample were:

- `pyanalyze`: 9
- `pycln`: 3
- `black`: 2
- `pydoctor`: 2
- `typeshed_client`: 2
- `pyupgrade`: 1
- `vulture`: 1
- `ast_decompiler`: 1

The raw scan is stored in `Misc/ast-nodevisitor-perf-data/usage-scan.json`.

## Benchmark corpus

Host interpreter: `/tmp/cpython-main-bench/python` built from `main`
at `cecf564073f`.

Workloads:

- `M1_dispatch_miss_flat`: dispatch-only, generic fallback, flat node list
- `M2_dispatch_hit_flat`: dispatch-only, common `visit_*` hits, flat node list
- `M3_recursive_generic`: recursive traversal with the stock `generic_visit`
- `R1_ast_unparse`: stdlib `_ast_unparse.Unparser`
- `R2_pygettext`: stdlib `Tools/i18n/pygettext.GettextVisitor`
- `R3_pycln_source_analyzer`: `pycln.utils.scan.SourceAnalyzer`
- `R4_pyupgrade_legacy`: `pyupgrade._plugins.legacy.Visitor`
- `R5_typeshed_name_extractor`: `typeshed_client.parser._NameExtractor`
- `R6_black_magicfinder`: `black.handle_ipynb_magics` visitors

Corpus sizes:

- CPython corpus: 9 files, 82,818 AST nodes
- `pycln`: 14 files
- `pyupgrade`: 16 files
- `typeshed_client`: 16 `.pyi` files
- synthetic notebook-magic corpus: 1,200 generated lines total

## Variant results

All results below use trimmed means. `baseline`, `name-cache`, and
`instance-cache` were each run twice and averaged. `class-cache` was
only run once because it was slower and less semantically compatible
than the other two caching approaches.

| Workload | baseline | name-cache | instance-cache | class-cache |
| --- | ---: | ---: | ---: | ---: |
| `M1_dispatch_miss_flat` | 338.305 ms | 224.240 (`-33.7%`) | 198.240 (`-41.4%`) | 288.526 (`-14.7%`) |
| `M2_dispatch_hit_flat` | 342.707 | 241.699 (`-29.5%`) | 195.671 (`-42.9%`) | 293.482 (`-14.4%`) |
| `M3_recursive_generic` | 225.585 | 184.691 (`-18.1%`) | 174.837 (`-22.5%`) | 199.751 (`-11.4%`) |
| `R1_ast_unparse` | 169.396 | 155.171 (`-8.4%`) | 162.723 (`-3.9%`) | 157.367 (`-7.1%`) |
| `R2_pygettext` | 156.114 | 131.582 (`-15.7%`) | 123.763 (`-20.7%`) | 138.132 (`-11.5%`) |
| `R3_pycln_source_analyzer` | 58.079 | 49.504 (`-14.8%`) | 52.193 (`-10.1%`) | 52.493 (`-9.6%`) |
| `R4_pyupgrade_legacy` | 68.680 | 58.742 (`-14.5%`) | 58.472 (`-14.9%`) | 60.781 (`-11.5%`) |
| `R5_typeshed_name_extractor` | 17.589 | 17.271 (`-1.8%`) | 15.847 (`-9.9%`) | 16.372 (`-6.9%`) |
| `R6_black_magicfinder` | 122.893 | 107.053 (`-12.9%`) | 107.114 (`-12.8%`) | 112.493 (`-8.5%`) |

## Semantic compatibility finding

`instance-cache` was the fastest overall variant, but it changes
current method lookup behavior:

- monkeypatching `visitor.visit_Name` after the first `Name` visit no
  longer takes effect for later `Name` nodes on that instance
- `__getattr__`-driven dynamic visitor lookup is only consulted once
  per node type instead of once per dispatch

That is not a theoretical concern; a simple repro shows:

- baseline: first `Name` visit uses `generic`, second uses patched
  `visit_Name`
- name-cache: same behavior as baseline
- instance-cache: both visits use the original cached method

To make that compatibility constraint explicit, this branch adds
`AST_Tests.test_nodevisitor_dynamic_method_lookup`.

## Chosen patch

The branch implements the **name-cache** design:

- module-level `_node_visitor_method_names`
- `NodeVisitor.visit()` reuses the memoized `"visit_" + node_type.__name__`
  string but still resolves the callable with `getattr(self, ...)`
  every time

That keeps the dynamic lookup semantics intact while still removing a
large amount of repeated string work from the hot path.

## Patched-file results

After patching `Lib/ast.py` directly and rerunning the benchmark twice,
the actual branch implementation averaged:

| Workload | baseline | patched file |
| --- | ---: | ---: |
| `M1_dispatch_miss_flat` | 338.305 ms | 235.458 (`-30.4%`) |
| `M2_dispatch_hit_flat` | 342.707 | 252.127 (`-26.4%`) |
| `M3_recursive_generic` | 225.585 | 190.195 (`-15.7%`) |
| `R1_ast_unparse` | 169.396 | 159.052 (`-6.1%`) |
| `R2_pygettext` | 156.114 | 132.570 (`-15.1%`) |
| `R3_pycln_source_analyzer` | 58.079 | 52.431 (`-9.7%`) |
| `R4_pyupgrade_legacy` | 68.680 | 59.896 (`-12.8%`) |
| `R5_typeshed_name_extractor` | 17.589 | 16.651 (`-5.3%`) |
| `R6_black_magicfinder` | 122.893 | 110.331 (`-10.2%`) |

## Validation

Using `/tmp/cpython-main-bench/python` with `PYTHONPATH` pointed at this
branch:

- `test.test_ast.test_ast`: **217 tests, all passed**
- `test.test_unparse`: passed
- `test.test_pyclbr`: passed
- `test.test_tools.test_i18n`: passed
- targeted new test:
  `AST_Tests.test_nodevisitor_dynamic_method_lookup`: passed

## Recommendation

`NodeVisitor.visit()` is still a worthwhile target, but the right first
patch is the conservative one:

1. **Ship the name-cache patch**. It keeps behavior, is tiny, and still
   shows meaningful wins on real visitors.
2. **Do not ship the instance-cache patch as-is**. It is faster, but it
   changes dynamic method lookup semantics for existing subclasses.
3. **Drop the class-cache direction**. It is less compatible than
   `name-cache` and not compelling enough to justify the extra risk.

## Raw data

Saved in `Misc/ast-nodevisitor-perf-data/`:

- `usage-scan.json`
- `baseline-run1.json`
- `baseline-run2.json`
- `name-cache-run1.json`
- `name-cache-run2.json`
- `instance-cache-run1.json`
- `instance-cache-run2.json`
- `class-cache-run1.json`
- `patched-name-cache.json`
- `patched-name-cache-run2.json`
