#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from collections import Counter, defaultdict
from pathlib import Path


ABC_IMPORT_MODULES = {"collections.abc", "abc"}
PROTOCOL_IMPORT_MODULES = {"typing", "typing_extensions"}
ABC_LIKE_NAMES = {
    "Awaitable",
    "Callable",
    "Collection",
    "Container",
    "Coroutine",
    "Generator",
    "Hashable",
    "Iterable",
    "Iterator",
    "Mapping",
    "MutableMapping",
    "MutableSequence",
    "MutableSet",
    "Reversible",
    "Sequence",
    "Set",
}


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        if base is not None:
            return f"{base}.{node.attr}"
    return None


class UsageVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imported_abc_names: set[str] = set()
        self.imported_protocol_names: set[str] = set()
        self.runtime_protocols: set[str] = set()
        self.protocols: set[str] = set()
        self.abc_bases: set[str] = set()
        self.instancecheck_calls: list[dict[str, object]] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module in ABC_IMPORT_MODULES:
            for alias in node.names:
                if alias.name in ABC_LIKE_NAMES or alias.name in {"ABC", "ABCMeta"}:
                    self.imported_abc_names.add(alias.asname or alias.name)
        if node.module in PROTOCOL_IMPORT_MODULES:
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name == "Protocol":
                    self.imported_protocol_names.add(local)
                elif alias.name == "runtime_checkable":
                    self.imported_protocol_names.add(local)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name
            if alias.name == "collections.abc":
                self.imported_abc_names.add(local)
            elif alias.name in PROTOCOL_IMPORT_MODULES:
                self.imported_protocol_names.add(local)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = {dotted_name(base) for base in node.bases}
        decorators = {dotted_name(dec) for dec in node.decorator_list}
        if any(base in self.imported_protocol_names or base == "Protocol" for base in bases):
            self.protocols.add(node.name)
            if (
                "runtime_checkable" in decorators
                or "typing.runtime_checkable" in decorators
                or "typing_extensions.runtime_checkable" in decorators
            ):
                self.runtime_protocols.add(node.name)
        if any(
            base in self.imported_abc_names
            or base in {"ABC", "ABCMeta", "abc.ABC", "abc.ABCMeta"}
            for base in bases
        ):
            self.abc_bases.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func_name = dotted_name(node.func)
        if func_name in {"isinstance", "issubclass"} and len(node.args) >= 2:
            targets = list(iter_target_names(node.args[1]))
            relevant = [
                target
                for target in targets
                if self._is_relevant_target(target)
            ]
            if relevant:
                self.instancecheck_calls.append(
                    {
                        "lineno": node.lineno,
                        "kind": func_name,
                        "targets": relevant,
                    }
                )
        self.generic_visit(node)

    def _is_relevant_target(self, target: str) -> bool:
        if target in self.runtime_protocols or target in self.protocols or target in self.abc_bases:
            return True
        if target in self.imported_abc_names or target in self.imported_protocol_names:
            return True
        if target.startswith("collections.abc."):
            return True
        if target.startswith("typing.") and target.endswith("Protocol"):
            return True
        return False


def iter_target_names(node: ast.AST):
    if isinstance(node, ast.Tuple):
        for elt in node.elts:
            yield from iter_target_names(elt)
        return
    name = dotted_name(node)
    if name is not None:
        yield name


def scan_file(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None
    visitor = UsageVisitor()
    visitor.visit(tree)
    if not (
        visitor.runtime_protocols
        or visitor.protocols
        or visitor.abc_bases
        or visitor.instancecheck_calls
    ):
        return None
    return {
        "runtime_protocols": sorted(visitor.runtime_protocols),
        "protocols": sorted(visitor.protocols),
        "abc_bases": sorted(visitor.abc_bases),
        "instancecheck_calls": visitor.instancecheck_calls,
    }


def scan_root(label: str, root: Path) -> tuple[list[dict[str, object]], Counter[str]]:
    findings: list[dict[str, object]] = []
    package_counts: Counter[str] = Counter()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        record = scan_file(path)
        if record is None:
            continue
        if rel.parts:
            package = rel.parts[0]
        else:
            package = path.stem
        package_counts[package] += len(record["instancecheck_calls"]) + len(record["runtime_protocols"])
        findings.append(
            {
                "root": label,
                "path": str(rel),
                **record,
            }
        )
    return findings, package_counts


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    stdlib_roots = [
        ("Lib", repo_root / "Lib"),
        ("Lib/test", repo_root / "Lib" / "test"),
        ("Tools", repo_root / "Tools"),
    ]
    site_packages = Path("/tmp/abc-instancecheck-venv/lib/python3.14/site-packages")

    findings: list[dict[str, object]] = []
    package_counts: Counter[str] = Counter()
    root_counts: dict[str, int] = {}
    for label, root in stdlib_roots + [("site-packages", site_packages)]:
        root_findings, root_package_counts = scan_root(label, root)
        root_counts[label] = len(root_findings)
        findings.extend(root_findings)
        package_counts.update(root_package_counts)

    findings.sort(key=lambda item: (item["root"], item["path"]))
    output = {
        "roots": root_counts,
        "package_counts": dict(sorted(package_counts.items(), key=lambda item: (-item[1], item[0]))),
        "files": findings,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
