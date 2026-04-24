from __future__ import annotations

import argparse
from pathlib import Path
import sys
import symtable

THIS_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = THIS_DIR.parent
if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

from helpers import CASE_SOURCES, measure_call, save_results


def build_cases() -> dict[str, tuple[int, callable]]:
    cases = {}
    inner_loops = {
        "S1_module_assign": 15_000,
        "S2_nested_functions": 6_000,
        "S3_class_methods": 5_000,
        "S4_comprehensions": 6_000,
        "S5_generic_function": 5_000,
        "S6_generic_class": 4_000,
    }
    for name, source in CASE_SOURCES.items():
        cases[name] = (
            inner_loops[name],
            lambda source=source, name=name: symtable.symtable(source, f"<{name}>", "exec"),
        )
    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--loops", type=int, default=11)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = {}
    for name, (inner_loops, func) in build_cases().items():
        cases[name] = measure_call(
            func,
            warmups=args.warmups,
            loops=args.loops,
            inner_loops=inner_loops,
        )
    save_results(
        args.output,
        {
            "warmups": args.warmups,
            "loops": args.loops,
            "cases": cases,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
