from __future__ import annotations

import gc
import json
import os
import statistics
import subprocess
import sys
import timeit
from pathlib import Path


class DummyPopen(subprocess.Popen):
    def __init__(self):
        pass

    def __del__(self):
        pass


def make_dummy():
    p = DummyPopen.__new__(DummyPopen)
    p._child_created = False
    p._closed_child_pipe_fds = False
    p.returncode = 0
    p.args = ["/bin/true"]
    return p


def trimmed_mean(runs):
    ordered = sorted(runs)
    if len(ordered) <= 2:
        return statistics.mean(ordered)
    return statistics.mean(ordered[1:-1])


def bench(fn, repeat=9):
    fn()
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        runs = timeit.repeat(fn, number=1, repeat=repeat)
    finally:
        if gc_was_enabled:
            gc.enable()
    return {
        "runs": runs,
        "min": min(runs),
        "median": statistics.median(runs),
        "trimmed_mean": trimmed_mean(runs),
    }


def setup_posix_spawn_common():
    orig_posix_spawn = os.posix_spawn
    orig_close = os.close

    def fake_spawn(executable, args, env, **kwargs):
        return 123

    def run():
        os.posix_spawn = fake_spawn
        os.close = lambda fd: None
        try:
            for _ in range(20000):
                p = make_dummy()
                subprocess.Popen._posix_spawn(
                    p, ["/bin/true"], "/bin/true", None, True, False,
                    -1, -1, -1, -1, -1, -1,
                )
        finally:
            os.posix_spawn = orig_posix_spawn
            os.close = orig_close

    return run


def setup_posix_spawn_pipe_actions():
    orig_posix_spawn = os.posix_spawn
    orig_close = os.close

    def fake_spawn(executable, args, env, **kwargs):
        return 123

    def run():
        os.posix_spawn = fake_spawn
        os.close = lambda fd: None
        try:
            for _ in range(20000):
                p = make_dummy()
                subprocess.Popen._posix_spawn(
                    p, ["/bin/true"], "/bin/true", None, True, True,
                    10, 11, 12, 13, 14, 15,
                )
        finally:
            os.posix_spawn = orig_posix_spawn
            os.close = orig_close

    return run


def setup_execute_child_common_str():
    def run():
        for _ in range(20000):
            p = make_dummy()

            def fake__posix_spawn(self, *args):
                self.pid = 123
                self._child_created = True

            p._posix_spawn = fake__posix_spawn.__get__(p, DummyPopen)
            subprocess.Popen._execute_child(
                p, ["/bin/true"], "/bin/true", None, False, (), None, None,
                None, 0, False, -1, -1, -1, -1, -1, -1,
                True, None, None, None, -1, False, -1,
            )

    return run


def setup_execute_child_common_bytes():
    def run():
        for _ in range(20000):
            p = make_dummy()

            def fake__posix_spawn(self, *args):
                self.pid = 123
                self._child_created = True

            p._posix_spawn = fake__posix_spawn.__get__(p, DummyPopen)
            subprocess.Popen._execute_child(
                p, [b"/bin/true"], b"/bin/true", None, False, (), None, None,
                None, 0, False, -1, -1, -1, -1, -1, -1,
                True, None, None, None, -1, False, -1,
            )

    return run


SCENARIOS = [
    ("S1_posix_spawn_common", setup_posix_spawn_common),
    ("S2_posix_spawn_pipe_actions", setup_posix_spawn_pipe_actions),
    ("S3_execute_child_common_str", setup_execute_child_common_str),
    ("S4_execute_child_common_bytes", setup_execute_child_common_bytes),
]


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    results = {"meta": {"label": label, "python": sys.version.split()[0]}}
    for name, setup in SCENARIOS:
        results[name] = bench(setup())
    if out:
        Path(out).write_text(json.dumps(results, indent=2, sort_keys=True))
    for name, _ in SCENARIOS:
        data = results[name]
        print(
            f"{name:28s} trimmed_mean={data['trimmed_mean']:.6f}s "
            f"min={data['min']:.6f}s"
        )


if __name__ == "__main__":
    main()
