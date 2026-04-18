from __future__ import annotations

from asyncio_eventloop_bench import (
    PlainASGIApp,
    UvicornLoopbackServer,
    micro_process_events,
    real_asyncio_echo,
    real_uvicorn_fastapi,
    real_uvicorn_plain,
)


def main() -> None:
    micro_process_events()
    if real_asyncio_echo(iterations=120) <= 0.0:
        raise RuntimeError("asyncio echo workload did not run")
    if real_uvicorn_plain(iterations=40, warmup=5) <= 0.0:
        raise RuntimeError("plain uvicorn workload did not run")
    if real_uvicorn_fastapi(iterations=25, warmup=4) <= 0.0:
        raise RuntimeError("fastapi uvicorn workload did not run")

    server = UvicornLoopbackServer(app=PlainASGIApp())
    server.start()
    server.stop()
    print("asyncio event-loop checks passed")


if __name__ == "__main__":
    main()
