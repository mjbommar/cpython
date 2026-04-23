from __future__ import annotations

import importlib
import json
import sys


scanner = importlib.import_module("json.scanner")
decoder_mod = importlib.import_module("json.decoder")


def make_decoder(**kwargs):
    old_make_scanner = scanner.make_scanner
    try:
        scanner.make_scanner = scanner.py_make_scanner
        return json.JSONDecoder(**kwargs)
    finally:
        scanner.make_scanner = old_make_scanner


failures = []


def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    line = f"{tag}  {name}" + (f"  -- {detail}" if detail else "")
    print(line)
    if not cond:
        failures.append(name)


pure = make_decoder()
check("scan_true", pure.scan_once("true", 0) == (True, 4))
check("scan_false", pure.scan_once("false", 0) == (False, 5))
check("scan_null", pure.scan_once("null", 0) == (None, 4))
check("scan_int", pure.scan_once("12345", 0) == (12345, 5))
check("scan_float", pure.scan_once("-12.5e+2", 0) == (-1250.0, 8))
check("scan_nan", pure.scan_once("NaN", 0)[1] == 3)
check("scan_infinity", pure.scan_once("Infinity", 0)[1] == 8)
check("scan_neg_infinity", pure.scan_once("-Infinity", 0)[1] == 9)
check(
    "scan_array",
    pure.scan_once('[1,true,null,"x"]', 0) == ([1, True, None, "x"], 17),
)
check(
    "scan_object",
    pure.scan_once('{"a":1,"b":[2,3]}', 0) == ({"a": 1, "b": [2, 3]}, 17),
)
check(
    "decode_nested",
    pure.decode('{"meta":{"ok":true},"items":[1,2,3],"name":"x"}')
    == {"meta": {"ok": True}, "items": [1, 2, 3], "name": "x"},
)

try:
    pure.scan_once("truX", 0)
    check("reject_bad_true", False, "accepted")
except StopIteration as err:
    check("reject_bad_true", err.value == 0, f"idx={err.value}")

try:
    pure.scan_once("-", 0)
    check("reject_bare_minus", False, "accepted")
except StopIteration as err:
    check("reject_bare_minus", err.value == 0, f"idx={err.value}")

if failures:
    print(f"FAILED {len(failures)} checks: {', '.join(failures)}")
    sys.exit(1)
print("all pure-scanner guardrails passed")
