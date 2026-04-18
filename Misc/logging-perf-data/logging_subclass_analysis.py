"""
Subclass-compatibility analysis for Lib/logging/__init__.py.

Passes:

1) AST-walk logging/__init__.py to enumerate all (class, method) pairs,
   flagging docstring-level "override in subclasses" hints.

2) For each .py file in the scanned venvs, build an import map so we
   know which names refer to `logging` vs. some other module (pygments
   has its own `Formatter` + `Filter`, joblib has its own `Logger`, etc).

3) Find classes that inherit from a *logging* class specifically and
   record which methods the subclass overrides.

Output: per-method override heat map + a "safe to accelerate in C"
candidate list.
"""

from __future__ import annotations

import ast
import collections
import json
from pathlib import Path


LOGGING_SOURCE = "/home/mjbommar/src/cpython/Lib/logging/__init__.py"

# Scan these for third-party subclasses
SCAN_ROOTS = [
    "/tmp/logging-broad-venv/lib/python3.15/site-packages",
    "/tmp/ignored-dir-unused/python3.15/site-packages",
]

# The logging classes we care about
LOGGING_CLASSES = {
    "Logger", "LogRecord", "Handler", "StreamHandler", "FileHandler",
    "NullHandler", "Formatter", "BufferingFormatter", "Filter", "Filterer",
    "LoggerAdapter", "LogRecordFactory", "Manager", "PlaceHolder",
    "PercentStyle", "StrFormatStyle", "StringTemplateStyle",
}


# ---------- Pass 1: enumerate stdlib logging methods ----------

def collect_stdlib_methods():
    src = open(LOGGING_SOURCE).read()
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in LOGGING_CLASSES:
            continue
        methods = {}
        for body in node.body:
            if isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(body) or ""
                hint = any(phrase in doc.lower() for phrase in [
                    "override", "extension point", "subclass",
                    "you can override", "override this", "factory method",
                ])
                methods[body.name] = {
                    "doc_first_line": doc.splitlines()[0] if doc else "",
                    "is_override_hint": hint,
                    "line": body.lineno,
                }
        out[node.name] = methods
    return out


# ---------- Pass 2: import-aware subclass detection ----------

def resolve_base(tree_body, base_node):
    """
    Walk the module's top-level imports to decide if `base_node` refers
    to a logging class. Returns the logging class name or None.
    """
    # Build a quick import map: local_name -> "logging:ClassName" or
    # "logging:Logger" etc. for anything sourced from logging or its
    # submodules.
    imports = {}
    for stmt in tree_body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if alias.name == "logging":
                    imports[alias.asname or "logging"] = "logging-module"
        elif isinstance(stmt, ast.ImportFrom):
            mod = stmt.module or ""
            # from logging import Logger, Handler, ...
            if mod == "logging":
                for alias in stmt.names:
                    local = alias.asname or alias.name
                    imports[local] = f"logging-cls:{alias.name}"
            # from logging.handlers import SomeHandler
            elif mod.startswith("logging."):
                for alias in stmt.names:
                    local = alias.asname or alias.name
                    imports[local] = f"logging-sub:{alias.name}"

    # Case A: Attribute access `logging.Formatter`
    if isinstance(base_node, ast.Attribute) and isinstance(base_node.value, ast.Name):
        module_alias = base_node.value.id
        if imports.get(module_alias) == "logging-module" and base_node.attr in LOGGING_CLASSES:
            return base_node.attr

    # Case B: Direct name `Formatter` after `from logging import Formatter`
    if isinstance(base_node, ast.Name):
        info = imports.get(base_node.id)
        if info and info.startswith("logging-cls:"):
            cls_name = info.split(":", 1)[1]
            if cls_name in LOGGING_CLASSES:
                return cls_name

    return None


def is_override_of_base(method_name, cls_name, stdlib):
    """True if method_name is a method of stdlib[cls_name] (i.e. override)."""
    return method_name in stdlib.get(cls_name, {})


def scan_file(path: Path, findings, stdlib, pkg_name: str):
    try:
        src = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    tree_body = tree.body
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            base_name = resolve_base(tree_body, base)
            if not base_name:
                continue
            overridden = []
            added = []
            for body in node.body:
                if isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if is_override_of_base(body.name, base_name, stdlib):
                        overridden.append(body.name)
                    else:
                        added.append(body.name)
            findings.append({
                "pkg": pkg_name,
                "file": str(path),
                "class": node.name,
                "base": base_name,
                "overrides": overridden,
                "custom_methods": added,
                "line": node.lineno,
            })


def pkg_name_from_path(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if rel.parts else "unknown"


def scan_roots(stdlib):
    findings = []
    files_scanned = 0
    for root_str in SCAN_ROOTS:
        root = Path(root_str)
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            files_scanned += 1
            pkg = pkg_name_from_path(root, py)
            scan_file(py, findings, stdlib, pkg)
    return findings, files_scanned


# ---------- Report ----------

def main():
    stdlib = collect_stdlib_methods()
    findings, nfiles = scan_roots(stdlib)

    subclasses_of = collections.defaultdict(list)
    for f in findings:
        subclasses_of[f["base"]].append(f)

    print(f"Scanned {nfiles} .py files across third-party venvs.")
    print(f"Found {len(findings)} subclasses of logging classes (import-aware).")
    print()

    # Per-base summary
    print("=" * 80)
    print("SUBCLASS COUNTS PER LOGGING BASE CLASS (import-verified)")
    print("=" * 80)
    for base in sorted(subclasses_of, key=lambda k: -len(subclasses_of[k])):
        hits = subclasses_of[base]
        pkgs = collections.Counter(h["pkg"] for h in hits)
        print(f"\n{base}: {len(hits)} subclasses across {len(pkgs)} packages")
        for pkg, count in pkgs.most_common():
            print(f"    {count:3d}× in {pkg}")

    # Method override heat map
    print()
    print("=" * 80)
    print("METHOD OVERRIDE HEAT MAP (per class, third-party only)")
    print("=" * 80)
    for cls in sorted(stdlib):
        methods = stdlib[cls]
        if not methods:
            continue
        subclass_methods = collections.Counter()
        subclass_method_pkgs = collections.defaultdict(set)
        for f in findings:
            if f["base"] == cls:
                for m in f["overrides"]:
                    subclass_methods[m] += 1
                    subclass_method_pkgs[m].add(f["pkg"])
        if not any(subclass_methods.values()) and cls not in subclasses_of:
            continue  # nothing subclassed, don't bother listing
        print(f"\n--- {cls} ({len(subclasses_of.get(cls, []))} subclasses) ---")
        print(f"  {'method':28s}  {'line':>5s}  {'hint':>4s}  {'overrides':>10s}  packages")
        for m in sorted(methods):
            info = methods[m]
            hint = "★" if info["is_override_hint"] else ""
            n = subclass_methods.get(m, 0)
            pkgs = ",".join(sorted(subclass_method_pkgs.get(m, set())))
            flag = f"{n}×" if n else ""
            print(f"  {m:28s}  {info['line']:>5d}  {hint:>4s}  {flag:>10s}  {pkgs}")

    # Classification
    print()
    print("=" * 80)
    print("C-ACCELERATION SAFETY CLASSIFICATION")
    print("=" * 80)

    def classify(cls, method):
        info = stdlib[cls][method]
        n = sum(1 for f in findings if f["base"] == cls and method in f["overrides"])
        hint = info["is_override_hint"]
        if method.startswith("__") and method != "__init__":
            return "dunder", n
        if hint:
            return "EXTENSION_POINT", n
        if n == 0:
            return "SAFE_TO_ACCELERATE", n
        if n <= 2:
            return "LIKELY_SAFE", n
        return "WIDELY_OVERRIDDEN", n

    buckets = collections.defaultdict(list)
    for cls in stdlib:
        for method in stdlib[cls]:
            cat, n = classify(cls, method)
            buckets[cat].append((cls, method, n))

    for cat in ("SAFE_TO_ACCELERATE", "LIKELY_SAFE", "WIDELY_OVERRIDDEN",
                "EXTENSION_POINT", "dunder"):
        entries = sorted(buckets.get(cat, []))
        if not entries:
            continue
        print(f"\n{cat}  ({len(entries)} methods):")
        for cls, method, n in entries:
            print(f"  {cls}.{method:30s}  overrides-seen={n}")


if __name__ == "__main__":
    main()
