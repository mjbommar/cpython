from __future__ import annotations

import ast
from collections import Counter, defaultdict
import json
from pathlib import Path


ROOTS = {
    "Lib": Path("Lib"),
    "Lib/test": Path("Lib/test"),
    "site-packages": Path("/tmp/perf-extra-pkgs"),
}

HEAPQ_ATTRS = {
    "heapify",
    "heappop",
    "heappush",
    "heappushpop",
    "heapreplace",
    "nsmallest",
    "nlargest",
}

EVENT_LOOP_ATTRS = {
    "call_at",
    "call_later",
}

PRIORITY_QUEUE_NAMES = {
    "PriorityQueue",
}


def classify_expr(node: ast.AST | None) -> str:
    if node is None:
        return "missing"
    if isinstance(node, ast.Tuple):
        return f"tuple_len_{len(node.elts)}"
    if isinstance(node, ast.Call):
        return "call"
    if isinstance(node, ast.Name):
        return "name"
    if isinstance(node, ast.Attribute):
        return "attribute"
    if isinstance(node, ast.Subscript):
        return "subscript"
    if isinstance(node, ast.Constant):
        return type(node.value).__name__
    return type(node).__name__.lower()


class UsageVisitor(ast.NodeVisitor):
    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.imported_heapq_funcs: set[str] = set()
        self.heapq_aliases: set[str] = set()
        self.counts: Counter[str] = Counter()
        self.heappush_shapes: Counter[str] = Counter()
        self.call_sites: list[dict[str, object]] = []

    def _record(self, kind: str, lineno: int, detail: str | None = None) -> None:
        item = {"kind": kind, "lineno": lineno}
        if detail is not None:
            item["detail"] = detail
        self.call_sites.append(item)
        self.counts[kind] += 1

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "heapq":
                self.heapq_aliases.add(alias.asname or alias.name)
                self._record("import_heapq", node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "heapq":
            for alias in node.names:
                self.imported_heapq_funcs.add(alias.asname or alias.name)
                self._record("import_from_heapq", node.lineno, alias.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name) and func.value.id in self.heapq_aliases:
                name = func.attr
                if name in HEAPQ_ATTRS:
                    self._record(f"heapq_{name}", node.lineno)
                    if name in {"heappush", "heapreplace", "heappushpop"}:
                        shape = classify_expr(node.args[1] if len(node.args) > 1 else None)
                        self.heappush_shapes[shape] += 1
                elif name in EVENT_LOOP_ATTRS:
                    self._record(name, node.lineno)
            elif func.attr in EVENT_LOOP_ATTRS:
                self._record(func.attr, node.lineno)
            elif func.attr in PRIORITY_QUEUE_NAMES:
                self._record("PriorityQueue", node.lineno)
        elif isinstance(func, ast.Name):
            name = func.id
            if name in self.imported_heapq_funcs:
                self._record(f"heapq_{name}", node.lineno)
                if name in {"heappush", "heapreplace", "heappushpop"}:
                    shape = classify_expr(node.args[1] if len(node.args) > 1 else None)
                    self.heappush_shapes[shape] += 1
            elif name in PRIORITY_QUEUE_NAMES:
                self._record("PriorityQueue", node.lineno)
        self.generic_visit(node)


def scan_file(path: Path, root_name: str, root_path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None
    relpath = str(path.relative_to(root_path))
    visitor = UsageVisitor(relpath=relpath)
    visitor.visit(tree)
    if not visitor.counts:
        return None
    top = relpath.split("/", 1)[0]
    return {
        "root": root_name,
        "package": top,
        "path": relpath,
        "counts": dict(visitor.counts),
        "heappush_shapes": dict(visitor.heappush_shapes),
        "call_sites": visitor.call_sites,
    }


def main() -> None:
    results: list[dict[str, object]] = []
    root_totals: Counter[str] = Counter()
    package_totals: Counter[str] = Counter()
    kind_totals: Counter[str] = Counter()
    shape_totals: Counter[str] = Counter()
    interesting_files: list[dict[str, object]] = []

    for root_name, root_path in ROOTS.items():
        for path in sorted(root_path.rglob("*.py")):
            if root_name == "Lib" and Path("Lib/test") in path.parents:
                continue
            item = scan_file(path, root_name, root_path)
            if item is None:
                continue
            results.append(item)
            total = sum(item["counts"].values())
            root_totals[root_name] += total
            package_totals[item["package"]] += total
            kind_totals.update(item["counts"])
            shape_totals.update(item["heappush_shapes"])
            interesting_files.append(
                {
                    "path": f"{root_name}/{item['path']}",
                    "total": total,
                    "counts": item["counts"],
                    "heappush_shapes": item["heappush_shapes"],
                }
            )

    payload = {
        "roots": dict(root_totals),
        "pattern_totals": dict(kind_totals),
        "heappush_shapes": dict(shape_totals),
        "top_packages": package_totals.most_common(20),
        "top_files": sorted(interesting_files, key=lambda item: (-item["total"], item["path"]))[:40],
        "files": results,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
