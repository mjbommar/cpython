from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
import re


PATTERNS = {
    "__getattr__": re.compile(r"\b__getattr__\b"),
    "__getattribute__": re.compile(r"\b__getattribute__\b"),
    "property": re.compile(r"@property|\bproperty\s*\("),
    "cached_property": re.compile(r"\bcached_property\b"),
    "getattr_call": re.compile(r"\bgetattr\s*\("),
    "hasattr_call": re.compile(r"\bhasattr\s*\("),
}


ROOTS = {
    "Lib": Path("Lib"),
    "Lib/test": Path("Lib/test"),
    "Tools": Path("Tools"),
    "site-packages": Path("/tmp/perf-extra-pkgs"),
}


def package_name(root_name: str, root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    if root_name == "site-packages" and rel.parts:
        return rel.parts[0]
    if root_name == "Lib/test" and rel.parts:
        return rel.parts[0]
    if rel.parts:
        return rel.parts[0]
    return path.name


def scan_file(path: Path) -> dict[str, int]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return {}
    counts = {}
    for name, pattern in PATTERNS.items():
        hits = len(pattern.findall(text))
        if hits:
            counts[name] = hits
    return counts


def main() -> None:
    root_counts = Counter()
    pattern_totals = Counter()
    package_counts = Counter()
    file_hits: dict[str, dict[str, int]] = {}

    for root_name, root in ROOTS.items():
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            counts = scan_file(path)
            if not counts:
                continue
            root_counts[root_name] += 1
            pattern_totals.update(counts)
            package_counts[package_name(root_name, root, path)] += sum(counts.values())
            file_hits[str(path)] = counts

    data = {
        "roots": dict(root_counts),
        "pattern_totals": dict(pattern_totals),
        "top_packages": package_counts.most_common(25),
        "top_files": sorted(
            file_hits.items(),
            key=lambda item: sum(item[1].values()),
            reverse=True,
        )[:40],
    }
    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
