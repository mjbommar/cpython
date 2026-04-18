"""
Run one of the service workloads under cProfile and print useful slices:

- top overall functions by cumulative time
- top stdlib/frozen functions by cumulative time
- top builtins/C-backed callables by cumulative time
"""

from __future__ import annotations

import argparse
import cProfile
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import pstats
import sys
import sysconfig
from typing import Iterable


THIS_DIR = Path(__file__).resolve().parent
WORKLOADS = {
    "fastapi": THIS_DIR / "fastapi_service_workload.py",
    "celery": THIS_DIR / "celery_service_workload.py",
}


@dataclass
class Entry:
    filename: str
    lineno: int
    funcname: str
    primitive_calls: int
    total_calls: int
    tottime: float
    cumtime: float


def load_workload(name: str):
    path = WORKLOADS[name]
    module_name = f"profile_workload_{name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load workload {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def iter_entries(stats: pstats.Stats) -> list[Entry]:
    rows: list[Entry] = []
    for (filename, lineno, funcname), (cc, nc, tt, ct, _callers) in stats.stats.items():
        rows.append(
            Entry(
                filename=filename,
                lineno=lineno,
                funcname=funcname,
                primitive_calls=cc,
                total_calls=nc,
                tottime=tt,
                cumtime=ct,
            )
        )
    rows.sort(key=lambda row: row.cumtime, reverse=True)
    return rows


def is_stdlib(entry: Entry, stdlib_dir: str) -> bool:
    filename = entry.filename
    return (
        filename.startswith(stdlib_dir)
        or filename.startswith("<frozen ")
        or filename.startswith("<built-in")
    )


def is_c_builtin(entry: Entry) -> bool:
    return entry.filename == "~" or entry.funcname.startswith("{")


def print_table(title: str, rows: Iterable[Entry], limit: int) -> None:
    print(f"\n{title}")
    print("  cumtime   tottime   calls    location")
    shown = 0
    for row in rows:
        print(
            f"  {row.cumtime:7.3f}   {row.tottime:7.3f}   "
            f"{row.primitive_calls:5d}/{row.total_calls:<5d}  "
            f"{row.filename}:{row.lineno}({row.funcname})"
        )
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        print("  <no rows>")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workload", choices=sorted(WORKLOADS))
    parser.add_argument("--iterations", type=int, default=None)
    parser.add_argument("--warmup", type=int, default=None)
    parser.add_argument("--celery-mode", choices=["worker", "eager"], default="eager")
    parser.add_argument("--sort", choices=["cumtime", "tottime"], default="cumtime")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--dump-stats", default=None)
    args = parser.parse_args()

    module = load_workload(args.workload)
    workload_kwargs = {}
    if args.workload == "celery":
        workload_kwargs["mode"] = args.celery_mode
    workload = module.create_workload(**workload_kwargs)

    iterations = args.iterations if args.iterations is not None else (
        3000 if args.workload == "fastapi" else 1500
    )
    warmup = args.warmup if args.warmup is not None else (
        300 if args.workload == "fastapi" else 100
    )

    try:
        workload.warmup(warmup)
        profiler = cProfile.Profile()
        profiler.enable()
        workload.run_iterations(iterations)
        profiler.disable()
    finally:
        workload.close()

    if args.dump_stats:
        profiler.dump_stats(args.dump_stats)

    stats = pstats.Stats(profiler)
    stats.sort_stats(args.sort)
    rows = iter_entries(stats)
    stdlib_dir = sysconfig.get_paths()["stdlib"]

    print(
        f"workload={args.workload} iterations={iterations} warmup={warmup} "
        f"sort={args.sort}"
    )
    print_table("Top Overall", rows, args.limit)
    print_table(
        "Top Stdlib/Frozen",
        (row for row in rows if is_stdlib(row, stdlib_dir)),
        args.limit,
    )
    print_table(
        "Top Builtins/C-backed",
        (row for row in rows if is_c_builtin(row)),
        args.limit,
    )


if __name__ == "__main__":
    main()
