from __future__ import annotations

import ast
from collections import Counter
import json
from pathlib import Path


ROOTS = {
    "Lib": Path("Lib"),
    "Lib/test": Path("Lib/test"),
    "site-packages": Path("/tmp/perf-extra-pkgs"),
}


def receiver_shape(node: ast.AST) -> str:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            value = node.value
            common = {
                "": "str_literal_empty",
                ",": "str_literal_comma",
                ", ": "str_literal_comma_space",
                " ": "str_literal_space",
                "\n": "str_literal_newline",
                "&": "str_literal_amp",
                ".": "str_literal_dot",
                ":": "str_literal_colon",
                "|": "str_literal_pipe",
            }
            if value in common:
                return common[value]
            return f"str_literal_len_{len(value)}"
        if isinstance(node.value, bytes):
            return "bytes_literal"
        return type(node.value).__name__
    if isinstance(node, ast.Name):
        return "name"
    if isinstance(node, ast.Attribute):
        return "attribute"
    if isinstance(node, ast.Call):
        return "call"
    if isinstance(node, ast.Subscript):
        return "subscript"
    if isinstance(node, ast.JoinedStr):
        return "fstring"
    return type(node).__name__.lower()


def arg_shape(node: ast.AST | None) -> str:
    if node is None:
        return "missing"
    if isinstance(node, ast.List):
        return f"list_len_{len(node.elts)}"
    if isinstance(node, ast.Tuple):
        return f"tuple_len_{len(node.elts)}"
    if isinstance(node, ast.ListComp):
        return "listcomp"
    if isinstance(node, ast.GeneratorExp):
        return "genexp"
    if isinstance(node, ast.Call):
        return "call"
    if isinstance(node, ast.Name):
        return "name"
    if isinstance(node, ast.Attribute):
        return "attribute"
    return type(node).__name__.lower()


def is_str_join_call(node: ast.Call) -> tuple[str, str] | None:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "join":
        return None
    return receiver_shape(func.value), arg_shape(node.args[0] if node.args else None)


def scan_file(path: Path, root_name: str, root_path: Path) -> dict[str, object] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return None

    counts: Counter[str] = Counter()
    receiver_counts: Counter[str] = Counter()
    arg_counts: Counter[str] = Counter()
    call_sites: list[dict[str, object]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        info = is_str_join_call(node)
        if info is None:
            continue
        receiver, arg = info
        counts["join"] += 1
        receiver_counts[receiver] += 1
        arg_counts[arg] += 1
        call_sites.append(
            {
                "lineno": node.lineno,
                "receiver": receiver,
                "arg": arg,
            }
        )

    if not counts:
        return None

    relpath = str(path.relative_to(root_path))
    package = relpath.split("/", 1)[0]
    return {
        "root": root_name,
        "package": package,
        "path": relpath,
        "counts": dict(counts),
        "receiver_counts": dict(receiver_counts),
        "arg_counts": dict(arg_counts),
        "call_sites": call_sites,
    }


def main() -> None:
    results: list[dict[str, object]] = []
    root_totals: Counter[str] = Counter()
    package_totals: Counter[str] = Counter()
    receiver_totals: Counter[str] = Counter()
    arg_totals: Counter[str] = Counter()
    top_files: list[dict[str, object]] = []

    for root_name, root_path in ROOTS.items():
        for path in sorted(root_path.rglob("*.py")):
            if root_name == "Lib" and Path("Lib/test") in path.parents:
                continue
            item = scan_file(path, root_name, root_path)
            if item is None:
                continue
            results.append(item)
            total = item["counts"]["join"]
            root_totals[root_name] += total
            package_totals[item["package"]] += total
            receiver_totals.update(item["receiver_counts"])
            arg_totals.update(item["arg_counts"])
            top_files.append(
                {
                    "path": f"{root_name}/{item['path']}",
                    "total": total,
                    "receiver_counts": item["receiver_counts"],
                    "arg_counts": item["arg_counts"],
                }
            )

    payload = {
        "roots": dict(root_totals),
        "receiver_totals": dict(receiver_totals),
        "arg_totals": dict(arg_totals),
        "top_packages": package_totals.most_common(20),
        "top_files": sorted(top_files, key=lambda row: (-row["total"], row["path"]))[:40],
        "files": results,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
