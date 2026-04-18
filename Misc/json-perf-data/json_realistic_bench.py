"""Realistic json bench — J1..J8, modeled on logging_realistic_bench.py.

Covers web-API encode/decode, log-shipping, NDJSON pipelines, bulk dumps,
Unicode-heavy payloads, numeric-heavy payloads, and cold-cache config loads.

Each scenario is a setup+body pair; the harness runs each body 7 times,
drops hi/lo, reports trimmed mean + min + per-call µs.
"""
import gc
import json
import os
import random
import statistics
import sys
import timeit
import uuid
from datetime import datetime, timezone


# ---------- payload factories ----------

def mk_s1_payload(seed=0):
    r = random.Random(seed)
    return {
        "id": str(uuid.UUID(int=r.getrandbits(128))),
        "ts": "2026-04-18T12:00:00Z",
        "user_id": r.randrange(10**6, 10**7),
        "ok": True,
        "latency_ms": r.random() * 120,
        "tags": ["web", "v2", "prod"],
        "meta": {"region": "us-east-1", "version": "1.42.0"},
        "items": [
            {"sku": f"SKU-{i:06d}", "qty": i, "price": i * 1.07, "in_stock": (i % 3) != 0}
            for i in range(10)
        ],
    }

def mk_s3_line():
    return {
        "ts": 1713456000.123456,
        "level": "INFO",
        "logger": "app.http",
        "msg": "served request",
        "req_id": "abc123def456",
        "path": "/v1/users/42",
        "status": 200,
        "latency_ms": 12.3,
        "extra": {"region": "us-east-1", "host": "api-7"},
    }

def mk_s5_line():
    return {
        "ts": "2026-04-17T10:00:00Z",
        "user_id": 123456,
        "event": "click",
        "path": "/a/b/c",
        "dur_ms": 12.3,
        "session": "abc123def",
        "country": "US",
        "ok": True,
        "a": 1, "b": 2, "c": 3, "d": 4,
    }

def mk_s6_bulk():
    return [mk_s5_line() for _ in range(100_000)]

def mk_s7_tree(depth, fanout):
    if depth == 0:
        return {"leaf": True, "v": depth}
    return {"d": depth, "kids": [mk_s7_tree(depth - 1, fanout) for _ in range(fanout)]}

def mk_s8_unicode():
    CJK = "日本語テスト絵文字😀🎉🚀中文测试한국어테스트"
    return [{"title": CJK + f" #{i}", "desc": CJK * 2, "id": i}
            for i in range(5_000)]

def mk_s9_numeric():
    r = random.Random(42)
    return [{"t": r.random() * 1e6,
             "x": r.uniform(-1e3, 1e3),
             "y": r.gauss(0, 1),
             "n": r.randrange(10**6, 10**10),
             "big": 10**60 + i}
            for i in range(20_000)]

def mk_s8_config():
    # A pyproject/OpenAPI-shaped config ~ 30KB
    return {
        "openapi": "3.0.0",
        "info": {"title": "Example API", "version": "1.0.0",
                 "description": "x" * 5000},
        "paths": {
            f"/v{v}/resource/{i}": {
                "get": {"summary": f"op{i}", "tags": [f"t{v}"],
                        "responses": {"200": {"description": "ok"}}},
                "post": {"summary": f"post{i}", "parameters": [
                    {"name": f"p{k}", "in": "query", "schema": {"type": "string"}}
                    for k in range(5)]},
            }
            for v in range(2) for i in range(50)
        },
    }


# ---------- scenarios ----------
# Each item: (id, setup, body, n)
# setup returns a dict of locals the body uses.

def setup_J1():
    p = mk_s1_payload()
    return {"dumps": json.dumps, "p": p}

def J1(ctx, n):
    dumps, p = ctx["dumps"], ctx["p"]
    for _ in range(n):
        dumps(p)

def setup_J2():
    p = mk_s3_line()
    return {"dumps": json.dumps, "p": p}

def J2(ctx, n):
    dumps, p = ctx["dumps"], ctx["p"]
    for _ in range(n):
        dumps(p)

def setup_J3():
    line = json.dumps(mk_s5_line())
    return {"loads": json.loads, "line": line}

def J3(ctx, n):
    loads, line = ctx["loads"], ctx["line"]
    for _ in range(n):
        loads(line)

def setup_J4():
    return {"dumps": json.dumps, "p": mk_s6_bulk()}

def J4(ctx, n):
    dumps, p = ctx["dumps"], ctx["p"]
    for _ in range(n):  # n=1 for this scenario
        dumps(p)

def setup_J5_ascii_true():
    return {"dumps": json.dumps, "p": mk_s8_unicode()}

def J5_ascii_true(ctx, n):
    dumps, p = ctx["dumps"], ctx["p"]
    for _ in range(n):
        dumps(p)  # ensure_ascii=True is default

def setup_J5_ascii_false():
    return {"dumps": json.dumps, "p": mk_s8_unicode()}

def J5_ascii_false(ctx, n):
    dumps, p = ctx["dumps"], ctx["p"]
    for _ in range(n):
        dumps(p, ensure_ascii=False)

def setup_J6():
    return {"dumps": json.dumps, "p": mk_s9_numeric()}

def J6(ctx, n):
    dumps, p = ctx["dumps"], ctx["p"]
    for _ in range(n):
        dumps(p)

def setup_J7():
    # Cold-ish: fresh config per call; but pre-built here so bench is stable
    return {"loads": json.loads, "s": json.dumps(mk_s8_config())}

def J7(ctx, n):
    loads, s = ctx["loads"], ctx["s"]
    for _ in range(n):
        loads(s)

def setup_J8():
    return {"dumps": json.dumps, "loads": json.loads,
            "p": mk_s7_tree(8, 3)}

def J8(ctx, n):
    dumps, loads, p = ctx["dumps"], ctx["loads"], ctx["p"]
    for _ in range(n):
        s = dumps(p)
        loads(s)


SCENARIOS = [
    ("J1_web_api_dumps",       setup_J1,             J1,               20_000),
    ("J2_log_line_dumps",      setup_J2,             J2,              100_000),
    ("J3_ndjson_loads",        setup_J3,             J3,              100_000),
    ("J4_bulk_dump_100k",      setup_J4,             J4,                    3),
    ("J5a_unicode_ascii=T",    setup_J5_ascii_true,  J5_ascii_true,         3),
    ("J5b_unicode_ascii=F",    setup_J5_ascii_false, J5_ascii_false,        3),
    ("J6_numeric_heavy",       setup_J6,             J6,                    3),
    ("J7_config_loads_cold",   setup_J7,             J7,                  500),
    ("J8_deep_tree_roundtrip", setup_J8,             J8,                  200),
]


def run(name, setup, body, n, repeat=7):
    ctx = setup()
    # one warm-up pass
    body(ctx, max(1, n // 100))
    gc_was = gc.isenabled()
    if name in {"J4_bulk_dump_100k", "J6_numeric_heavy"}:
        gc.disable()
    try:
        runs = timeit.repeat(lambda: body(ctx, n), number=1, repeat=repeat)
    finally:
        if gc_was: gc.enable()
    runs.sort()
    trimmed = runs[1:-1]
    return {
        "n": n,
        "runs": runs,
        "min": min(runs),
        "median": statistics.median(runs),
        "trimmed_mean": statistics.mean(trimmed),
    }


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    filter_ = sys.argv[3] if len(sys.argv) > 3 else None

    print(f"\n== {label} (python={sys.version_info.major}.{sys.version_info.minor}) ==")
    results = {}
    for sid, setup, body, n in SCENARIOS:
        if filter_ and filter_ not in sid:
            continue
        r = run(sid, setup, body, n)
        results[sid] = r
        per_call_us = r["trimmed_mean"] * 1e6 / n
        print(f"  {sid:28s} n={n:6d}  "
              f"trimmed_mean={r['trimmed_mean']:.4f}s  "
              f"min={r['min']:.4f}s  per_call={per_call_us:10.3f}us")
    if out:
        with open(out, "w") as f:
            json.dump(results, f, indent=2)
