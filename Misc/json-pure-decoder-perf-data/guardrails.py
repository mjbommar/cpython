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
check("line_decode", pure.decode('{"a":1,"b":2,"c":[3,true,null]}') == {"a": 1, "b": 2, "c": [3, True, None]})
check("duplicate_last_wins", pure.decode('{"x":1,"x":2,"y":3}') == {"x": 2, "y": 3})
check("whitespace_raw_decode", pure.raw_decode(' \n\t{"x":1}', 3) == ({"x": 1}, 10))
check("negative_number", pure.decode('{"x":-12.5}') == {"x": -12.5})
check("nan_constant", pure.decode('{"x":NaN}')["x"] != pure.decode('{"x":NaN}')["x"])
check("array_hook", make_decoder(array_hook=tuple).decode('[1,2,3]') == (1, 2, 3))
check("object_hook", make_decoder(object_hook=lambda d: ("wrapped", d)).decode('{"a":1}') == ("wrapped", {"a": 1}))
check(
    "object_pairs_hook",
    make_decoder(object_pairs_hook=tuple).decode('{"a":1,"b":2}') == (("a", 1), ("b", 2)),
)
check(
    "object_pairs_hook_priority",
    make_decoder(object_hook=lambda d: "bad", object_pairs_hook=tuple).decode('{"a":1}') == (("a", 1),),
)
check(
    "jsonobject_direct",
    decoder_mod.JSONObject(('{"a":1,"b":2}', 1), True, pure.scan_once, None, None, {}) == ({"a": 1, "b": 2}, 13),
)
try:
    pure.decode('{"a":1,}')
    check("reject_trailing_comma", False, "accepted")
except json.JSONDecodeError:
    check("reject_trailing_comma", True)
try:
    pure.decode('{"a" 1}')
    check("reject_missing_colon", False, "accepted")
except json.JSONDecodeError:
    check("reject_missing_colon", True)

if failures:
    print(f"FAILED {len(failures)} checks: {', '.join(failures)}")
    sys.exit(1)
print("all pure-decoder guardrails passed")
