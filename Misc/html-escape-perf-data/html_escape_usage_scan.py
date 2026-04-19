from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOTS = [
    Path("Lib"),
    Path("Lib/test"),
    Path("/tmp/perf-extra-pkgs"),
]


def classify_expr(node: ast.AST | None) -> str:
    if node is None:
        return "missing"
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return "const_str"
        return type(node.value).__name__
    if isinstance(node, ast.Name):
        return "name"
    if isinstance(node, ast.Attribute):
        return "attr"
    if isinstance(node, ast.Call):
        return "call"
    if isinstance(node, ast.JoinedStr):
        return "fstring"
    if isinstance(node, ast.Subscript):
        return "subscript"
    if isinstance(node, ast.BinOp):
        return type(node.op).__name__
    if isinstance(node, (ast.List, ast.Tuple)):
        return type(node).__name__.lower()
    return type(node).__name__


class EscapeVisitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.calls = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        matched = False
        if isinstance(func, ast.Attribute) and func.attr == "escape":
            if isinstance(func.value, ast.Name) and func.value.id == "html":
                matched = True
        if matched:
            quote_kind = "default"
            if len(node.args) >= 2:
                arg = node.args[1]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, bool):
                    quote_kind = str(arg.value)
                else:
                    quote_kind = classify_expr(arg)
            for keyword in node.keywords:
                if keyword.arg == "quote":
                    if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, bool):
                        quote_kind = str(keyword.value.value)
                    else:
                        quote_kind = classify_expr(keyword.value)
                    break
            self.calls.append(
                {
                    "path": str(self.path),
                    "line": node.lineno,
                    "arg_kind": classify_expr(node.args[0]) if node.args else "missing",
                    "quote_kind": quote_kind,
                }
            )
        self.generic_visit(node)


def package_name(path: str) -> str:
    parts = Path(path).parts
    if not parts:
        return "<unknown>"
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "tmp" and parts[2] == "perf-extra-pkgs":
        return parts[3] if len(parts) >= 4 else "perf-extra-pkgs"
    if parts[0] == "Lib":
        return "stdlib"
    if parts[0] == "tmp" and len(parts) >= 3 and parts[1] == "perf-extra-pkgs":
        return parts[2]
    return parts[0]


def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    visitor = EscapeVisitor(path)
    visitor.visit(tree)
    return visitor.calls


def main() -> None:
    calls = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            calls.extend(scan_file(path))

    by_package = Counter()
    arg_kinds = Counter()
    quote_kinds = Counter()
    by_file = defaultdict(int)
    for call in calls:
        by_package[package_name(call["path"])] += 1
        arg_kinds[call["arg_kind"]] += 1
        quote_kinds[call["quote_kind"]] += 1
        by_file[call["path"]] += 1

    result = {
        "total_calls": len(calls),
        "top_packages": by_package.most_common(20),
        "arg_kinds": arg_kinds.most_common(),
        "quote_kinds": quote_kinds.most_common(),
        "top_files": Counter(by_file).most_common(25),
        "sample_calls": calls[:50],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
