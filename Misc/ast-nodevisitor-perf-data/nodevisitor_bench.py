#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import importlib
import importlib.util
import io
import json
import statistics
import sys
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace


MISS = object()
GENERIC = object()


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def apply_baseline(ast_mod: ModuleType) -> None:
    return


def apply_name_cache(ast_mod: ModuleType) -> None:
    name_cache: dict[type, str] = {}

    def visit(self, node):
        node_type = node.__class__
        method = name_cache.get(node_type)
        if method is None:
            method = "visit_" + node_type.__name__
            name_cache[node_type] = method
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    ast_mod.NodeVisitor.visit = visit


def apply_instance_cache(ast_mod: ModuleType) -> None:
    def visit(self, node):
        cache = self.__dict__.get("_nodevisitor_visit_cache")
        if cache is None:
            cache = {}
            self.__dict__["_nodevisitor_visit_cache"] = cache
        node_type = node.__class__
        visitor = cache.get(node_type, MISS)
        if visitor is MISS:
            visitor = getattr(self, "visit_" + node_type.__name__, self.generic_visit)
            cache[node_type] = visitor
        return visitor(node)

    ast_mod.NodeVisitor.visit = visit


def apply_class_cache(ast_mod: ModuleType) -> None:
    def resolve(visitor_cls: type, node_type: type):
        method = "visit_" + node_type.__name__
        for base in visitor_cls.__mro__:
            namespace = base.__dict__
            if method in namespace:
                return namespace[method]
        return GENERIC

    def visit(self, node):
        visitor_cls = type(self)
        cache = visitor_cls.__dict__.get("_nodevisitor_class_cache")
        if cache is None:
            cache = {}
            setattr(visitor_cls, "_nodevisitor_class_cache", cache)
        node_type = node.__class__
        visitor = cache.get(node_type, MISS)
        if visitor is MISS:
            visitor = resolve(visitor_cls, node_type)
            cache[node_type] = visitor
        if visitor is GENERIC:
            return self.generic_visit(node)
        return visitor(self, node)

    ast_mod.NodeVisitor.visit = visit


VARIANTS = {
    "baseline": apply_baseline,
    "name-cache": apply_name_cache,
    "instance-cache": apply_instance_cache,
    "class-cache": apply_class_cache,
}


def trimmed_mean(samples: list[float]) -> float:
    if len(samples) <= 2:
        return statistics.mean(samples)
    ordered = sorted(samples)
    return statistics.mean(ordered[1:-1])


def bench(fn, *, samples: int = 7) -> dict[str, float | list[float]]:
    runs = []
    fn()
    for _ in range(samples):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return {
        "runs": runs,
        "min": min(runs),
        "median": statistics.median(runs),
        "trimmed_mean": trimmed_mean(runs),
    }


def read_files(paths: list[Path]) -> list[str]:
    out = []
    for path in paths:
        try:
            out.append(path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
    return out


def largest_files(root: Path, suffix: str, limit: int) -> list[Path]:
    paths = sorted(root.rglob(f"*{suffix}"), key=lambda p: p.stat().st_size, reverse=True)
    return paths[:limit]


def build_line_magic_source() -> str:
    snippets = []
    for i in range(300):
        snippets.append(
            "get_ipython().run_line_magic('matplotlib', 'inline')\n"
            "get_ipython().system('echo hello')\n"
            f"x_{i} = get_ipython().getoutput('echo hello')\n"
        )
    return "".join(snippets)


def build_cell_magic_source() -> str:
    snippets = []
    for _ in range(300):
        snippets.append(
            "get_ipython().run_cell_magic('time', '', 'print(1)\\n')\n"
        )
    return "".join(snippets)


def make_generic_dispatch_visitor(ast_mod: ModuleType):
    class GenericDispatchVisitor(ast_mod.NodeVisitor):
        def generic_visit(self, node):
            return None

    return GenericDispatchVisitor


def make_hit_dispatch_visitor(ast_mod: ModuleType):
    class HitDispatchVisitor(ast_mod.NodeVisitor):
        def generic_visit(self, node):
            return None

        visit_Name = generic_visit
        visit_Attribute = generic_visit
        visit_Call = generic_visit
        visit_Constant = generic_visit
        visit_FunctionDef = generic_visit
        visit_AsyncFunctionDef = generic_visit
        visit_ClassDef = generic_visit
        visit_Import = generic_visit
        visit_ImportFrom = generic_visit
        visit_Assign = generic_visit

    return HitDispatchVisitor


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=sorted(VARIANTS), required=True)
    parser.add_argument("--worktree", type=Path, default=Path.cwd())
    parser.add_argument(
        "--site-packages",
        type=Path,
        default=Path("/tmp/ast-nodevisitor-venv/lib/python3.14/site-packages"),
    )
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()

    ast_mod = load_module("bench_ast", args.worktree / "Lib" / "ast.py")
    VARIANTS[args.variant](ast_mod)
    sys.modules["ast"] = ast_mod
    sys.path.insert(0, str(args.site_packages))

    ast_unparse = load_module("bench_ast_unparse", args.worktree / "Lib" / "_ast_unparse.py")
    pygettext = load_module("bench_pygettext", args.worktree / "Tools" / "i18n" / "pygettext.py")
    pycln_scan = importlib.import_module("pycln.utils.scan")
    pyupgrade_mod = importlib.import_module("pyupgrade._plugins.legacy")
    black_magics = importlib.import_module("black.handle_ipynb_magics")
    typeshed_parser = importlib.import_module("typeshed_client.parser")

    cpython_files = [
        args.worktree / "Lib" / "ast.py",
        args.worktree / "Lib" / "_ast_unparse.py",
        args.worktree / "Lib" / "typing.py",
        args.worktree / "Lib" / "dataclasses.py",
        args.worktree / "Lib" / "inspect.py",
        args.worktree / "Lib" / "pyclbr.py",
        args.worktree / "Lib" / "test" / "test_ast" / "test_ast.py",
        args.worktree / "Tools" / "i18n" / "pygettext.py",
        args.worktree / "Tools" / "clinic" / "libclinic" / "dsl_parser.py",
    ]
    cpython_sources = read_files(cpython_files)
    cpython_trees = [ast_mod.parse(src) for src in cpython_sources]
    cpython_nodes = [node for tree in cpython_trees for node in ast_mod.walk(tree)]

    pycln_sources = read_files(largest_files(args.site_packages / "pycln", ".py", 16))
    pycln_trees = [ast_mod.parse(src) for src in pycln_sources]

    pyupgrade_sources = read_files(largest_files(args.site_packages / "pyupgrade", ".py", 16))
    pyupgrade_trees = [ast_mod.parse(src) for src in pyupgrade_sources]

    typeshed_root = args.site_packages / "typeshed_client" / "typeshed"
    typeshed_sources = read_files(largest_files(typeshed_root, ".pyi", 16))
    typeshed_trees = [ast_mod.parse(src) for src in typeshed_sources]

    line_magic_source = build_line_magic_source()
    line_magic_tree = ast_mod.parse(line_magic_source)
    cell_magic_source = build_cell_magic_source()
    cell_magic_tree = ast_mod.parse(cell_magic_source)

    GenericDispatchVisitor = make_generic_dispatch_visitor(ast_mod)
    HitDispatchVisitor = make_hit_dispatch_visitor(ast_mod)

    def dispatch_miss():
        visitor = GenericDispatchVisitor()
        for _ in range(25):
            for node in cpython_nodes:
                visitor.visit(node)

    def dispatch_hit():
        visitor = HitDispatchVisitor()
        for _ in range(25):
            for node in cpython_nodes:
                visitor.visit(node)

    def recursive_generic():
        class RecursiveVisitor(ast_mod.NodeVisitor):
            pass

        for _ in range(6):
            visitor = RecursiveVisitor()
            for tree in cpython_trees:
                visitor.visit(tree)

    def unparse_cpython():
        for _ in range(3):
            for tree in cpython_trees:
                visitor = ast_unparse.Unparser()
                visitor.visit(tree)

    gettext_options = SimpleNamespace(
        comment_tags=None,
        docstrings=False,
        nodocstrings={},
        keywords={},
    )

    def pygettext_cpython():
        for _ in range(4):
            for index, tree in enumerate(cpython_trees):
                visitor = pygettext.GettextVisitor(gettext_options)
                visitor.filename = f"cpython_{index}.py"
                visitor.visit(tree)

    def pycln_source_analyzer():
        for _ in range(6):
            for tree in pycln_trees:
                visitor = pycln_scan.SourceAnalyzer()
                visitor.visit(tree)

    def pyupgrade_legacy_workload():
        for _ in range(6):
            for tree in pyupgrade_trees:
                visitor = pyupgrade_mod.Visitor()
                visitor.visit(tree)

    search_context = typeshed_parser.get_search_context()
    module_path = typeshed_parser.ModulePath(("bench",))

    def typeshed_name_extractor():
        with contextlib.redirect_stderr(io.StringIO()):
            for index, tree in enumerate(typeshed_trees):
                visitor = typeshed_parser._NameExtractor(
                    search_context,
                    module_path,
                    file_path=typeshed_root / f"bench_{index}.pyi",
                    is_init=False,
                )
                list(visitor.visit(tree))

    def black_magic_finder():
        for _ in range(20):
            visitor = black_magics.MagicFinder()
            visitor.visit(line_magic_tree)
            cell_visitor = black_magics.CellMagicFinder()
            cell_visitor.visit(cell_magic_tree)

    workloads = {
        "M1_dispatch_miss_flat": dispatch_miss,
        "M2_dispatch_hit_flat": dispatch_hit,
        "M3_recursive_generic": recursive_generic,
        "R1_ast_unparse": unparse_cpython,
        "R2_pygettext": pygettext_cpython,
        "R3_pycln_source_analyzer": pycln_source_analyzer,
        "R4_pyupgrade_legacy": pyupgrade_legacy_workload,
        "R5_typeshed_name_extractor": typeshed_name_extractor,
        "R6_black_magicfinder": black_magic_finder,
    }

    metadata = {
        "variant": args.variant,
        "cpython_files": len(cpython_trees),
        "cpython_nodes": len(cpython_nodes),
        "pycln_files": len(pycln_trees),
        "pyupgrade_files": len(pyupgrade_trees),
        "typeshed_files": len(typeshed_trees),
        "line_magic_lines": len(line_magic_source.splitlines()),
        "cell_magic_lines": len(cell_magic_source.splitlines()),
        "python": sys.version,
    }

    results = {
        "metadata": metadata,
        "results": {
            name: bench(workload, samples=args.samples)
            for name, workload in workloads.items()
        },
    }
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
