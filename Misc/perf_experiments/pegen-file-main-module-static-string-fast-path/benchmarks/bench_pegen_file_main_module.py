#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
FAMILY_ROOT = THIS_FILE.parents[1]
if str(FAMILY_ROOT) not in sys.path:
    sys.path.insert(0, str(FAMILY_ROOT))

from helpers import make_case_files, run_case, save_results, temporary_case_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, default=Path("./python"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "Misc/perf_experiments/pegen-file-main-module-static-string-fast-path/benchmarks/results/runtime-baseline.json"
        ),
    )
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--loops", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    python = args.python.resolve()
    with temporary_case_dir() as tmp:
        cases = make_case_files(Path(tmp))
        results = {
            "python": str(python),
            "warmups": args.warmups,
            "loops": args.loops,
            "cases": {},
        }
        for name, script in cases.items():
            results["cases"][name] = run_case(
                python,
                script,
                warmups=args.warmups,
                loops=args.loops,
            )
        save_results(args.output.resolve(), results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
