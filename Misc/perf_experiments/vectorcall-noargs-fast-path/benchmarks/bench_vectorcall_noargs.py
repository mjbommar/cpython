from __future__ import annotations

import argparse
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = THIS_DIR.parent
if str(EXPERIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_DIR))

from helpers import measure_call, save_results


def plain_noargs() -> int:
    return 1


def closure_noargs_factory():
    x = 5

    def inner() -> int:
        return x

    return inner


class NoArgMethod:
    def __init__(self, value: int) -> None:
        self.value = value

    def method(self) -> int:
        return self.value


def defaults_not_noargs(x: int = 7, y: int = 9) -> int:
    return x + y


def onearg(x: int) -> int:
    return x + 1


def build_cases() -> dict[str, tuple[int, callable]]:
    closure = closure_noargs_factory()
    bound = NoArgMethod(11).method

    return {
        "V1_plain_noargs": (2_000_000, plain_noargs),
        "V2_bound_method_noargs": (1_500_000, bound),
        "V3_closure_noargs": (1_500_000, closure),
        "V4_defaults_called_noargs": (1_200_000, defaults_not_noargs),
        "V5_onearg_control": (1_200_000, lambda: onearg(5)),
    }


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
