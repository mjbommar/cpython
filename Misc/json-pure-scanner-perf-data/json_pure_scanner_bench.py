from __future__ import annotations

import gc
import importlib
import json
import statistics
import sys
import timeit


scanner = importlib.import_module("json.scanner")


def make_decoder(**kwargs):
    old_make_scanner = scanner.make_scanner
    try:
        scanner.make_scanner = scanner.py_make_scanner
        return json.JSONDecoder(**kwargs)
    finally:
        scanner.make_scanner = old_make_scanner


LINE_OBJ = {
    "ts": "2026-04-23T12:00:00Z",
    "user_id": 123456,
    "event": "click",
    "path": "/a/b/c",
    "dur_ms": 12.3,
    "session": "abc123def",
    "country": "US",
    "ok": True,
    "a": 1,
    "b": 2,
    "c": 3,
    "d": 4,
}
NESTED_OBJ = {
    "root": {
        "meta": {"region": "us-east-1", "service": "api"},
        "users": [
            {"id": i, "name": f"user-{i}", "active": (i % 2 == 0)}
            for i in range(40)
        ],
        "flags": {"alpha": True, "beta": False, "gamma": None},
    },
    "paths": {f"/v1/{i}": {"limit": i, "enabled": True} for i in range(30)},
}

LINE_JSON = json.dumps(LINE_OBJ, separators=(",", ":"))
NESTED_JSON = json.dumps(NESTED_OBJ, separators=(",", ":"))
TOKEN_ARRAY = '[true,false,null,12345,-12.5e+2,"token",{"k":1}]'
TOKEN_OBJECT = '{"a":true,"b":false,"c":null,"d":12345,"e":-12.5e+2}'


def trimmed_mean(runs):
    ordered = sorted(runs)
    if len(ordered) <= 2:
        return statistics.mean(ordered)
    return statistics.mean(ordered[1:-1])


def bench(fn, repeat=7):
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


def setup_scan_constants():
    decoder = make_decoder()
    scan = decoder.scan_once
    tokens = ("true", "false", "null", "NaN", "Infinity", "-Infinity")

    def run():
        for _ in range(100_000):
            for token in tokens:
                scan(token, 0)

    return run


def setup_scan_numbers():
    decoder = make_decoder()
    scan = decoder.scan_once
    tokens = ("0", "12345", "-9999", "12.5", "-12.5e+2", "0.03125e-1")

    def run():
        for _ in range(100_000):
            for token in tokens:
                scan(token, 0)

    return run


def setup_scan_array():
    decoder = make_decoder()
    scan = decoder.scan_once
    token = TOKEN_ARRAY

    def run():
        for _ in range(50_000):
            scan(token, 0)

    return run


def setup_scan_object():
    decoder = make_decoder()
    scan = decoder.scan_once
    token = TOKEN_OBJECT

    def run():
        for _ in range(50_000):
            scan(token, 0)

    return run


def setup_decode_line():
    decoder = make_decoder()
    decode = decoder.decode
    token = LINE_JSON

    def run():
        for _ in range(100_000):
            decode(token)

    return run


def setup_decode_nested():
    decoder = make_decoder()
    decode = decoder.decode
    token = NESTED_JSON

    def run():
        for _ in range(10_000):
            decode(token)

    return run


SCENARIOS = [
    ("S1_scan_constants", setup_scan_constants),
    ("S2_scan_numbers", setup_scan_numbers),
    ("S3_scan_array", setup_scan_array),
    ("S4_scan_object", setup_scan_object),
    ("S5_decode_line", setup_decode_line),
    ("S6_decode_nested", setup_decode_nested),
]


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    results = {"meta": {"label": label, "python": sys.version.split()[0]}}
    for name, setup in SCENARIOS:
        results[name] = bench(setup())
    if out:
        from pathlib import Path

        Path(out).write_text(json.dumps(results, indent=2, sort_keys=True))
    for name, _ in SCENARIOS:
        data = results[name]
        print(
            f"{name:20s} trimmed_mean={data['trimmed_mean']:.6f}s "
            f"min={data['min']:.6f}s"
        )


if __name__ == "__main__":
    main()
