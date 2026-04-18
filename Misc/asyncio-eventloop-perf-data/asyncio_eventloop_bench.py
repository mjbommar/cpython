from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
import math
from pathlib import Path
import selectors
import socket
import statistics
import threading
import time

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn


def _noop(*args: object) -> None:
    return None


class PlainASGIApp:
    body = b'{"ok":true,"kind":"plain"}'

    async def __call__(self, scope, receive, send):
        assert scope["type"] == "http"
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(self.body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": self.body})


class ItemIn(BaseModel):
    item_id: int
    qty: int = Field(ge=1, le=20)
    price_cents: int = Field(ge=1)
    tags: list[str]
    owner: str
    coupon: bool = False


class ItemOut(BaseModel):
    item_id: int
    total_cents: int
    labels: list[str]


fastapi_app = FastAPI()


@fastapi_app.post("/items/{route_item_id}", response_model=ItemOut)
async def create_item(route_item_id: int, item: ItemIn) -> ItemOut:
    subtotal = item.price_cents * item.qty
    discount = 250 if item.coupon else 0
    total = subtotal * 3 - discount
    labels = [f"{item.owner}:{tag.upper()}" for tag in item.tags]
    return ItemOut(item_id=route_item_id, total_cents=total, labels=labels)


@dataclass
class UvicornLoopbackServer:
    app: object
    port: int | None = None
    server: uvicorn.Server | None = None
    thread: threading.Thread | None = None
    sock: socket.socket | None = None

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(512)
        config = uvicorn.Config(
            self.app,
            host="127.0.0.1",
            port=0,
            loop="asyncio",
            lifespan="off",
            access_log=False,
            log_level="warning",
            workers=1,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(
            target=server.run,
            kwargs={"sockets": [sock]},
            daemon=True,
        )
        thread.start()
        deadline = time.perf_counter() + 10.0
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("uvicorn thread exited before startup")
            if time.perf_counter() > deadline:
                raise RuntimeError("uvicorn server failed to start")
            time.sleep(0.01)
        self.sock = sock
        self.server = server
        self.thread = thread
        self.port = sock.getsockname()[1]

    def stop(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=10.0)
        if self.sock is not None:
            self.sock.close()


def micro_call_later_heap() -> None:
    loop = asyncio.new_event_loop()
    try:
        base = loop.time() + 3600.0
        for i in range(40_000):
            loop.call_at(base + ((i % 23) * 1e-6), _noop)
    finally:
        loop.close()


def micro_due_timer_run_once() -> None:
    loop = asyncio.new_event_loop()
    try:
        now = loop.time()
        for i in range(12_000):
            loop.call_at(now - ((i % 7) * 1e-6), _noop)
        loop._run_once()
    finally:
        loop.close()


def micro_cancelled_timer_cleanup() -> None:
    loop = asyncio.new_event_loop()
    try:
        base = loop.time() + 600.0
        handles = [loop.call_at(base + i * 1e-6, _noop) for i in range(20_000)]
        for handle in handles[::2]:
            handle.cancel()
        loop.call_soon(_noop)
        loop._run_once()
    finally:
        loop.close()


def micro_process_events() -> None:
    loop = asyncio.new_event_loop()
    try:
        reader = asyncio.events.Handle(_noop, (), loop)
        writer = asyncio.events.Handle(_noop, (), loop)
        key = selectors.SelectorKey(
            fileobj=11,
            fd=11,
            events=selectors.EVENT_READ | selectors.EVENT_WRITE,
            data=(reader, writer),
        )
        event_list = [(key, selectors.EVENT_READ | selectors.EVENT_WRITE)] * 20_000
        loop._process_events(event_list)
        expected = 40_000
        actual = len(loop._ready)
        if actual != expected:
            raise RuntimeError(f"unexpected ready size: {actual} != {expected}")
    finally:
        loop.close()


def real_selector_socketpair() -> None:
    selector = selectors.EpollSelector()
    pairs = [socket.socketpair() for _ in range(48)]
    try:
        for reader, writer in pairs:
            reader.setblocking(False)
            writer.setblocking(False)
            selector.register(reader, selectors.EVENT_READ)
        for _ in range(120):
            for _, writer in pairs:
                writer.send(b"x")
            ready = selector.select(0)
            for key, _ in ready:
                key.fileobj.recv(1)
    finally:
        selector.close()
        for reader, writer in pairs:
            reader.close()
            writer.close()


async def _asyncio_echo_once(iterations: int, payload_size: int) -> float:
    payload = (b"x" * payload_size)

    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await reader.readexactly(payload_size)
                writer.write(data)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        for _ in range(50):
            writer.write(payload)
            await writer.drain()
            if await reader.readexactly(payload_size) != payload:
                raise RuntimeError("echo mismatch in warmup")
        t0 = time.perf_counter()
        for _ in range(iterations):
            writer.write(payload)
            await writer.drain()
            if await reader.readexactly(payload_size) != payload:
                raise RuntimeError("echo mismatch")
        elapsed = time.perf_counter() - t0
        writer.close()
        await writer.wait_closed()
        return elapsed
    finally:
        server.close()
        await server.wait_closed()


def real_asyncio_echo(iterations: int = 1200, payload_size: int = 64) -> float:
    return asyncio.run(_asyncio_echo_once(iterations=iterations, payload_size=payload_size))


def real_uvicorn_plain(iterations: int = 40, warmup: int = 5) -> float:
    app = PlainASGIApp()
    server = UvicornLoopbackServer(app=app)
    server.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.port}",
            timeout=5.0,
            trust_env=False,
        ) as client:
            for _ in range(warmup):
                response = client.get("/")
                if response.status_code != 200 or response.content != app.body:
                    raise RuntimeError("plain uvicorn warmup failed")
            t0 = time.perf_counter()
            for _ in range(iterations):
                response = client.get("/")
                if response.status_code != 200 or response.content != app.body:
                    raise RuntimeError("plain uvicorn request failed")
            return time.perf_counter() - t0
    finally:
        server.stop()


def real_uvicorn_fastapi(iterations: int = 30, warmup: int = 4) -> float:
    server = UvicornLoopbackServer(app=fastapi_app)
    server.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.port}",
            timeout=5.0,
            trust_env=False,
        ) as client:
            for i in range(warmup):
                payload = {
                    "item_id": i,
                    "qty": (i % 5) + 1,
                    "price_cents": 1200 + (i % 11),
                    "tags": ["fast", "loop", f"t{i % 7}"],
                    "owner": f"user{i % 13}",
                    "coupon": bool(i % 11 == 0),
                }
                response = client.post(f"/items/{i % 1000}", json=payload)
                if response.status_code != 200 or b"total_cents" not in response.content:
                    raise RuntimeError("fastapi uvicorn warmup failed")
            t0 = time.perf_counter()
            for i in range(iterations):
                payload = {
                    "item_id": i,
                    "qty": (i % 5) + 1,
                    "price_cents": 1200 + (i % 11),
                    "tags": ["fast", "loop", f"t{i % 7}"],
                    "owner": f"user{i % 13}",
                    "coupon": bool(i % 11 == 0),
                }
                response = client.post(f"/items/{i % 1000}", json=payload)
                if response.status_code != 200 or b"total_cents" not in response.content:
                    raise RuntimeError("fastapi uvicorn request failed")
            return time.perf_counter() - t0
    finally:
        server.stop()


WORKLOADS = {
    "M1_call_later_heap": micro_call_later_heap,
    "M2_due_timer_run_once": micro_due_timer_run_once,
    "M3_cancelled_timer_cleanup": micro_cancelled_timer_cleanup,
    "M4_process_events": micro_process_events,
    "R1_selector_socketpair": real_selector_socketpair,
    "R2_asyncio_echo": real_asyncio_echo,
    "R3_uvicorn_plain": real_uvicorn_plain,
    "R4_uvicorn_fastapi": real_uvicorn_fastapi,
}


def time_one(fn):
    result = fn()
    if isinstance(result, (int, float)):
        return float(result)
    return None


def run_benchmark(fn, samples: int) -> dict[str, object]:
    measured = []
    for _ in range(samples):
        result = time_one(fn)
        if result is None:
            t0 = time.perf_counter()
            fn()
            result = time.perf_counter() - t0
        measured.append(result)
    if len(measured) > 4:
        trimmed = sorted(measured)[1:-1]
    else:
        trimmed = measured
    return {
        "samples_s": measured,
        "trimmed_mean_s": statistics.mean(trimmed),
        "min_s": min(measured),
        "max_s": max(measured),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()

    results = {}
    for name, fn in WORKLOADS.items():
        results[name] = run_benchmark(fn, samples=args.samples)

    payload = {
        "label": args.label,
        "python": (
            f"executable={Path(__import__('sys').executable)}\n"
            f"version={__import__('sys').version}\n"
            f"cwd={Path.cwd()}"
        ),
        "workloads": results,
    }
    output_path = Path(args.output)
    output_path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
