from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SITE_PACKAGES = Path("/tmp/perf-extra-pkgs")


def pkg_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    if root.name == "Lib" and rel.parts[0] == "test":
        return f"test/{rel.parts[1] if len(rel.parts) > 1 else rel.parts[0]}"
    return rel.parts[0]


def call_target_kind(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return "name"
    if isinstance(node, ast.Attribute):
        return "attribute"
    if isinstance(node, ast.Call):
        return "call"
    if isinstance(node, ast.Subscript):
        return "subscript"
    if isinstance(node, ast.Lambda):
        return "lambda"
    return "other"


def pos_bucket(n: int) -> str:
    if n <= 5:
        return str(n)
    if n <= 8:
        return "6-8"
    return "9+"


def kw_bucket(n: int) -> str:
    if n <= 3:
        return str(n)
    return "4+"


class Visitor(ast.NodeVisitor):
    def __init__(self, counters: dict[str, Counter[str]], package: str) -> None:
        self.counters = counters
        self.package = package

    def visit_Call(self, node: ast.Call) -> None:
        posargs = 0
        has_starargs = False
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                has_starargs = True
            else:
                posargs += 1
        kwcount = 0
        has_kw_unpack = False
        for kw in node.keywords:
            if kw.arg is None:
                has_kw_unpack = True
            else:
                kwcount += 1

        self.counters["call_target_kind"][call_target_kind(node.func)] += 1
        self.counters["call_pos_bucket"][pos_bucket(posargs)] += 1
        self.counters["call_kw_bucket"][kw_bucket(kwcount)] += 1
        self.counters["call_has_starargs"][str(has_starargs)] += 1
        self.counters["call_has_kw_unpack"][str(has_kw_unpack)] += 1
        self.counters["call_method_like"][str(isinstance(node.func, ast.Attribute))] += 1
        simple_positional = not has_starargs and not has_kw_unpack and kwcount == 0
        self.counters["call_simple_positional"][str(simple_positional)] += 1
        if simple_positional:
            self.counters["simple_positional_bucket"][pos_bucket(posargs)] += 1
        self.counters["call_top_packages"][self.package] += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node)
        self.generic_visit(node)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        posonly = len(args.posonlyargs)
        poskw = len(args.args)
        kwonly = len(args.kwonlyargs)
        defaults = len(args.defaults)
        self.counters["func_posonly_bucket"][pos_bucket(posonly)] += 1
        self.counters["func_poskw_bucket"][pos_bucket(poskw)] += 1
        self.counters["func_kwonly_bucket"][kw_bucket(kwonly)] += 1
        self.counters["func_defaults_bucket"][kw_bucket(defaults)] += 1
        self.counters["func_has_varargs"][str(args.vararg is not None)] += 1
        self.counters["func_has_varkw"][str(args.kwarg is not None)] += 1
        simple = kwonly == 0 and args.vararg is None and args.kwarg is None
        self.counters["func_simple_signature"][str(simple)] += 1
        self.counters["func_top_packages"][self.package] += 1


def scan_root(root: Path) -> dict[str, Counter[str]]:
    counters: dict[str, Counter[str]] = {
        "call_target_kind": Counter(),
        "call_pos_bucket": Counter(),
        "call_kw_bucket": Counter(),
        "call_has_starargs": Counter(),
        "call_has_kw_unpack": Counter(),
        "call_method_like": Counter(),
        "call_simple_positional": Counter(),
        "simple_positional_bucket": Counter(),
        "call_top_packages": Counter(),
        "func_posonly_bucket": Counter(),
        "func_poskw_bucket": Counter(),
        "func_kwonly_bucket": Counter(),
        "func_defaults_bucket": Counter(),
        "func_has_varargs": Counter(),
        "func_has_varkw": Counter(),
        "func_simple_signature": Counter(),
        "func_top_packages": Counter(),
    }
    for path in root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        Visitor(counters, pkg_name(root, path)).visit(tree)
    return counters


def to_jsonable(counters: dict[str, Counter[str]]) -> dict[str, dict[str, int]]:
    return {name: dict(counter.most_common()) for name, counter in counters.items()}


def main() -> None:
    roots: dict[str, Path] = {"Lib": ROOT / "Lib"}
    if SITE_PACKAGES.exists():
        roots["site-packages"] = SITE_PACKAGES

    output: dict[str, object] = {"roots": {}, "scans": {}}
    for name, root in roots.items():
        counters = scan_root(root)
        output["roots"][name] = str(root)
        output["scans"][name] = to_jsonable(counters)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
