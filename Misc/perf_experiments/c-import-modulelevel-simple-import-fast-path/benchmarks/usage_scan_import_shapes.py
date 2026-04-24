#!/usr/bin/env python3
"""Census import-statement shapes across the stdlib."""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path


def is_test_path(path: Path) -> bool:
    parts = path.parts
    return "test" in parts or "idle_test" in parts


def scan_file(path: Path, counts: Counter[str]) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        counts["parse_skipped"] += 1
        return

    counts["files"] += 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            counts["import_nodes"] += 1
            for alias in node.names:
                counts["import_aliases"] += 1
                if "." in alias.name:
                    counts["import_dotted_aliases"] += 1
                else:
                    counts["import_plain_aliases"] += 1
        elif isinstance(node, ast.ImportFrom):
            counts["from_nodes"] += 1
            if node.level:
                counts["from_relative_nodes"] += 1
            else:
                counts["from_absolute_nodes"] += 1
            if node.module and "." in node.module:
                counts["from_dotted_module_nodes"] += 1
            elif node.module:
                counts["from_plain_module_nodes"] += 1
            for alias in node.names:
                counts["from_aliases"] += 1
                if alias.name == "*":
                    counts["from_star_aliases"] += 1


def summarize(counts: Counter[str]) -> dict[str, object]:
    import_aliases = counts["import_aliases"] or 1
    from_nodes = counts["from_nodes"] or 1
    return {
        "files": counts["files"],
        "parse_skipped": counts["parse_skipped"],
        "import_nodes": counts["import_nodes"],
        "import_aliases": counts["import_aliases"],
        "import_plain_aliases": counts["import_plain_aliases"],
        "import_dotted_aliases": counts["import_dotted_aliases"],
        "import_plain_share": round(counts["import_plain_aliases"] / import_aliases, 4),
        "import_dotted_share": round(counts["import_dotted_aliases"] / import_aliases, 4),
        "from_nodes": counts["from_nodes"],
        "from_absolute_nodes": counts["from_absolute_nodes"],
        "from_relative_nodes": counts["from_relative_nodes"],
        "from_plain_module_nodes": counts["from_plain_module_nodes"],
        "from_dotted_module_nodes": counts["from_dotted_module_nodes"],
        "from_aliases": counts["from_aliases"],
        "from_star_aliases": counts["from_star_aliases"],
        "from_absolute_share": round(counts["from_absolute_nodes"] / from_nodes, 4),
        "from_relative_share": round(counts["from_relative_nodes"] / from_nodes, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lib", type=Path, default=Path("Lib"))
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--json", action="store_true")
    ns = parser.parse_args()

    counts: Counter[str] = Counter()
    for path in sorted(ns.lib.rglob("*.py")):
        if not ns.include_tests and is_test_path(path):
            continue
        scan_file(path, counts)

    result = summarize(counts)
    if ns.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return

    for key in (
        "files",
        "parse_skipped",
        "import_nodes",
        "import_aliases",
        "import_plain_aliases",
        "import_dotted_aliases",
        "import_plain_share",
        "import_dotted_share",
        "from_nodes",
        "from_absolute_nodes",
        "from_relative_nodes",
        "from_plain_module_nodes",
        "from_dotted_module_nodes",
        "from_aliases",
        "from_star_aliases",
        "from_absolute_share",
        "from_relative_share",
    ):
        print(f"{key}: {result[key]}")


if __name__ == "__main__":
    main()
