# AST `NodeVisitor` Perf Data

Raw artifacts backing `Misc/ast-nodevisitor-perf-diary.md`.

## Scripts

- `nodevisitor_usage_scan.py` scans a set of roots and reports direct
  and local-derived subclasses of `ast.NodeVisitor`.
- `nodevisitor_bench.py` benchmarks candidate `NodeVisitor.visit()`
  refactors against synthetic dispatch loops and real stdlib /
  third-party visitor workloads.

## Intended workflow

1. Build or reuse a CPython interpreter for a stable host binary.
2. Run `nodevisitor_usage_scan.py` over the stdlib and a third-party
   sample environment.
3. Run `nodevisitor_bench.py --variant ...` for each candidate.
4. Save the JSON outputs in this directory and summarize them in the
   diary.
