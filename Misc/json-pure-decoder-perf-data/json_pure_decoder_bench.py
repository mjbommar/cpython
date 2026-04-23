from __future__ import annotations

import gc
import importlib
import json
import statistics
import sys
import timeit


scanner = importlib.import_module("json.scanner")
decoder_mod = importlib.import_module("json.decoder")


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

LARGE_OBJECT = {f"k{i:03d}": i for i in range(120)}
DUPLICATE_KEYS = '{"x": 1, "y": 2, "x": 3, "z": 4}'
WHITESPACE_OBJECT = ' \n\t  ' + json.dumps(LINE_OBJ)
LINE_JSON = json.dumps(LINE_OBJ, separators=(",", ":"))
NESTED_JSON = json.dumps(NESTED_OBJ, separators=(",", ":"))
LARGE_JSON = json.dumps(LARGE_OBJECT, separators=(",", ":"))


def trimmed_mean(runs):
    ordered = sorted(runs)
    if len(ordered) <= 2:
        return statistics.mean(ordered)
    return statistics.mean(ordered[1:-1])


def bench(name, fn, repeat=7):
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


def setup_decode_line():
    decoder = make_decoder()

    def run():
        decode = decoder.decode
        s = LINE_JSON
        for _ in range(100_000):
            decode(s)

    return run


def setup_decode_nested():
    decoder = make_decoder()

    def run():
        decode = decoder.decode
        s = NESTED_JSON
        for _ in range(10_000):
            decode(s)

    return run


def setup_raw_decode_whitespace():
    decoder = make_decoder()

    def run():
        raw_decode = decoder.raw_decode
        s = WHITESPACE_OBJECT
        idx = decoder_mod.WHITESPACE.match(s, 0).end()
        for _ in range(100_000):
            raw_decode(s, idx)

    return run


def setup_object_direct_large():
    decoder = make_decoder()

    def run():
        obj_scan = decoder.scan_once
        parse = decoder_mod.JSONObject
        s = LARGE_JSON
        for _ in range(50_000):
            parse((s, 1), True, obj_scan, None, None, {})

    return run


def setup_object_direct_duplicate():
    decoder = make_decoder()

    def run():
        obj_scan = decoder.scan_once
        parse = decoder_mod.JSONObject
        s = DUPLICATE_KEYS
        for _ in range(100_000):
            parse((s, 1), True, obj_scan, None, None, {})

    return run


def setup_object_pairs_hook():
    decoder = make_decoder(object_pairs_hook=tuple)

    def run():
        decode = decoder.decode
        s = LINE_JSON
        for _ in range(50_000):
            decode(s)

    return run


SCENARIOS = [
    ("P1_decode_line", setup_decode_line),
    ("P2_decode_nested", setup_decode_nested),
    ("P3_raw_decode_whitespace", setup_raw_decode_whitespace),
    ("P4_object_direct_large", setup_object_direct_large),
    ("P5_object_direct_duplicate", setup_object_direct_duplicate),
    ("P6_object_pairs_hook", setup_object_pairs_hook),
]


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "bench"
    out = sys.argv[2] if len(sys.argv) > 2 else None
    results = {"meta": {"label": label, "python": sys.version.split()[0]}}
    for name, setup in SCENARIOS:
        results[name] = bench(name, setup())
    if out:
        import json as _json
        from pathlib import Path
        Path(out).write_text(_json.dumps(results, indent=2, sort_keys=True))
    for name, _ in SCENARIOS:
        data = results[name]
        print(
            f"{name:26s} trimmed_mean={data['trimmed_mean']:.6f}s "
            f"min={data['min']:.6f}s"
        )


if __name__ == "__main__":
    main()
