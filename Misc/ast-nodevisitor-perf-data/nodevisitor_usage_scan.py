#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import json
import warnings
from collections import Counter, defaultdict
from pathlib import Path


def _read(path: Path) -> str | None:
    try:
        return path.read_text("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _matches_ast_nodevisitor(
    node: ast.expr,
    ast_aliases: set[str],
    imported_names: set[str],
    local_subclasses: set[str],
) -> bool:
    if isinstance(node, ast.Name):
        return node.id in imported_names or node.id in local_subclasses
    if isinstance(node, ast.Attribute) and node.attr == "NodeVisitor":
        return isinstance(node.value, ast.Name) and node.value.id in ast_aliases
    return False


def analyze_file(path: Path) -> dict[str, object] | None:
    text = _read(path)
    if text is None:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None

    ast_aliases = set()
    imported_names = set()
    classes: list[ast.ClassDef] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "ast":
                    ast_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "ast":
            for alias in node.names:
                if alias.name == "NodeVisitor":
                    imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node)

    local_subclasses = set()
    changed = True
    while changed:
        changed = False
        for classdef in classes:
            if classdef.name in local_subclasses:
                continue
            if any(
                _matches_ast_nodevisitor(base, ast_aliases, imported_names, local_subclasses)
                for base in classdef.bases
            ):
                local_subclasses.add(classdef.name)
                changed = True

    if not local_subclasses:
        return None

    hits = []
    for classdef in classes:
        if classdef.name not in local_subclasses:
            continue
        bases = [ast.unparse(base) for base in classdef.bases]
        hits.append(
            {
                "class": classdef.name,
                "line": classdef.lineno,
                "bases": bases,
            }
        )

    return {
        "path": str(path),
        "classes": hits,
    }


def package_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    by_root: dict[str, list[dict[str, object]]] = defaultdict(list)
    package_counts: Counter[str] = Counter()

    for root in args.roots:
        for path in root.rglob("*.py"):
            hit = analyze_file(path)
            if hit is None:
                continue
            root_key = str(root)
            by_root[root_key].append(hit)
            package_counts[package_name(root, path)] += len(hit["classes"])  # type: ignore[arg-type]

    summary = {
        "roots": [str(root) for root in args.roots],
        "package_counts": dict(package_counts.most_common()),
        "files": by_root,
    }

    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    for root, hits in by_root.items():
        print(root)
        print(f"  files with ast.NodeVisitor subclasses: {len(hits)}")
    print("Top packages:")
    for pkg, count in package_counts.most_common(25):
        print(f"  {pkg}: {count}")


if __name__ == "__main__":
    main()
