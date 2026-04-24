#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
FAMILY_ROOT = THIS_FILE.parents[1]
if str(FAMILY_ROOT) not in sys.path:
    sys.path.insert(0, str(FAMILY_ROOT))

from helpers import DEFAULT_INNER_LOOPS, parse_cases, run_case, save_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "Misc/perf_experiments/compile-ast-compile-structural-fast-path/benchmarks/results/source-baseline.json"
        ),
    )
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--loops", type=int, default=9)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = parse_cases()
    results = {
        "warmups": args.warmups,
        "loops": args.loops,
        "cases": {},
    }
    for name, tree in cases.items():
        results["cases"][name] = run_case(
            tree,
            warmups=args.warmups,
            loops=args.loops,
            inner_loops=DEFAULT_INNER_LOOPS[name],
        )
    save_results(args.output.resolve(), results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
