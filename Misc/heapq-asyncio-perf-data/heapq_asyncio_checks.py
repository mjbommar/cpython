from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_module():
    path = Path(__file__).with_name("heapq_asyncio_bench.py")
    spec = importlib.util.spec_from_file_location("heapq_asyncio_bench", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    mod = load_module()
    mod.micro_namedtuple3_pushpop()
    mod.micro_sched_event_pushpop()
    mod.micro_due_timer_run_once()
    mod.real_sched_run()
    mod.real_dateutil_rruleset()
    mod.real_kombu_timer()
    if mod.real_asyncio_echo(iterations=120, payload_size=64) <= 0:
        raise RuntimeError("asyncio echo check failed")
    if mod.real_uvicorn_plain(iterations=10, warmup=3) <= 0:
        raise RuntimeError("uvicorn plain check failed")
    if mod.real_uvicorn_fastapi(iterations=8, warmup=3) <= 0:
        raise RuntimeError("uvicorn fastapi check failed")
    print("heapq/asyncio checks passed")


if __name__ == "__main__":
    main()
