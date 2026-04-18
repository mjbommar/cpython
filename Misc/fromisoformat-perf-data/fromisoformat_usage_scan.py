#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path


TARGETS = {
    "date.fromisoformat",
    "datetime.fromisoformat",
    "time.fromisoformat",
}


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        if base is not None:
            return f"{base}.{node.attr}"
    return None


def scan_file(path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None

    calls = []
    imported_datetime_names: set[str] = set()
    imported_module_aliases: set[str] = set()

    class Visitor(ast.NodeVisitor):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if node.module == "datetime":
                for alias in node.names:
                    if alias.name in {"date", "datetime", "time"}:
                        imported_datetime_names.add(alias.asname or alias.name)
            self.generic_visit(node)

        def visit_Import(self, node: ast.Import) -> None:
            for alias in node.names:
                if alias.name == "datetime":
                    imported_module_aliases.add(alias.asname or alias.name)
            self.generic_visit(node)

        def visit_Call(self, node: ast.Call) -> None:
            target = dotted_name(node.func)
            if target in TARGETS:
                calls.append({"lineno": node.lineno, "target": target})
            elif target is not None:
                head = target.split(".", 1)[0]
                if head in imported_module_aliases and target.endswith(".fromisoformat"):
                    calls.append({"lineno": node.lineno, "target": target})
                elif head in imported_datetime_names and target.endswith(".fromisoformat"):
                    calls.append({"lineno": node.lineno, "target": target})
                elif target.endswith(".fromisoformat"):
                    calls.append({"lineno": node.lineno, "target": target})
            self.generic_visit(node)

    Visitor().visit(tree)
    if not calls:
        return None
    return {"calls": calls}


def scan_root(label: str, root: Path) -> tuple[list[dict[str, object]], Counter[str]]:
    findings = []
    package_counts: Counter[str] = Counter()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        record = scan_file(path)
        if record is None:
            continue
        package = rel.parts[0] if rel.parts else path.stem
        package_counts[package] += len(record["calls"])
        findings.append({"root": label, "path": str(rel), **record})
    return findings, package_counts


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    roots = [
        ("Lib", repo_root / "Lib"),
        ("Lib/test", repo_root / "Lib" / "test"),
        ("Tools", repo_root / "Tools"),
        ("site-packages", Path("/tmp/abc-instancecheck-venv/lib/python3.14/site-packages")),
    ]
    findings = []
    package_counts: Counter[str] = Counter()
    root_counts = {}
    for label, root in roots:
        root_findings, root_package_counts = scan_root(label, root)
        findings.extend(root_findings)
        package_counts.update(root_package_counts)
        root_counts[label] = len(root_findings)

    findings.sort(key=lambda item: (item["root"], item["path"]))
    output = {
        "roots": root_counts,
        "package_counts": dict(sorted(package_counts.items(), key=lambda item: (-item[1], item[0]))),
        "files": findings,
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
