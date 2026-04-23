from __future__ import annotations

import os
import subprocess
import sys


failures = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    line = f"{tag}  {name}" + (f"  -- {detail}" if detail else "")
    print(line)
    if not cond:
        failures.append(name)


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


orig_posix_spawn = os.posix_spawn
orig_close = os.close


def record_spawn(calls):
    def fake_spawn(executable, args, env, **kwargs):
        calls.append((executable, args, env, kwargs))
        return 123
    return fake_spawn


try:
    os.close = lambda fd: None

    calls = []
    os.posix_spawn = record_spawn(calls)
    p = make_dummy()
    subprocess.Popen._posix_spawn(
        p, ["/bin/true"], "/bin/true", None, True, False,
        -1, -1, -1, -1, -1, -1,
    )
    kwargs = calls.pop()[3]
    check("posix_spawn_restore_signals", "setsigdef" in kwargs)
    check("posix_spawn_no_file_actions", "file_actions" not in kwargs)
    check("close_pipe_fds_fast_noop", p._closed_child_pipe_fds)

    calls = []
    os.posix_spawn = record_spawn(calls)
    p = make_dummy()
    subprocess.Popen._posix_spawn(
        p, ["/bin/true"], "/bin/true", None, True, True,
        10, 11, 12, 13, 14, 15,
    )
    kwargs = calls.pop()[3]
    expected = [
        (os.POSIX_SPAWN_CLOSE, 11),
        (os.POSIX_SPAWN_CLOSE, 12),
        (os.POSIX_SPAWN_CLOSE, 14),
        (os.POSIX_SPAWN_DUP2, 10, 0),
        (os.POSIX_SPAWN_DUP2, 13, 1),
        (os.POSIX_SPAWN_DUP2, 15, 2),
        (os.POSIX_SPAWN_CLOSEFROM, 3),
    ]
    check("posix_spawn_file_actions", kwargs.get("file_actions") == expected)

    p = make_dummy()
    seen = {}

    def fake__posix_spawn(self, args, executable, env, restore_signals, close_fds,
                          p2cread, p2cwrite, c2pread, c2pwrite, errread, errwrite):
        seen["args"] = args
        seen["executable"] = executable
        seen["env"] = env
        self.pid = 123
        self._child_created = True

    p._posix_spawn = fake__posix_spawn.__get__(p, DummyPopen)
    subprocess.Popen._execute_child(
        p, ["/bin/true"], "/bin/true", None, False, (), None, None,
        None, 0, False, -1, -1, -1, -1, -1, -1,
        True, None, None, None, -1, False, -1,
    )
    check("execute_child_fast_path_args", seen.get("args") == ["/bin/true"])
    check("execute_child_fast_path_exec", seen.get("executable") == "/bin/true")

finally:
    os.posix_spawn = orig_posix_spawn
    os.close = orig_close


if failures:
    print(f"FAILED {len(failures)} checks: {', '.join(failures)}")
    sys.exit(1)
print("all subprocess spawn guardrails passed")
