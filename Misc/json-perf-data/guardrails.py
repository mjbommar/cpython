"""json optimization guardrails — the 15-check battery from agent S.

Run BEFORE every bench. Any failure is a correctness regression;
the experiment is rejected until fixed. Exit 1 on any failure.
"""
import json
import enum
import math
import sys


failures = []

def check(name, cond, detail=""):
    tag = "PASS" if cond else "FAIL"
    line = f"{tag}  {name}" + (f"  — {detail}" if detail else "")
    print(line)
    if not cond:
        failures.append(name)


# --- §2 self-check battery ---

class IE(enum.IntEnum):
    X = 1

class SS(str):
    pass

class LS(list):
    def __iter__(self):
        # Reverse iteration as a visible override
        for x in reversed(list.__iter__.__get__(self)()):
            yield x

class LSIter(list):
    # Subclass whose __iter__ reverses — must be honored.
    def __iter__(self):
        # Use list.__iter__ explicitly to avoid recursion via list(self).
        items = [list.__getitem__(self, i) for i in range(list.__len__(self))]
        return iter(items[::-1])

class DS(dict):
    # Subclass with overridden items() AND a real item so the
    # empty-dict short-circuit in encoder_listencode_dict doesn't fire.
    def __init__(self):
        super().__init__()
        super().__setitem__('__real', 0)
    def items(self):
        return [('z', 1), ('a', 2)]


# 1. bool must emit 'true'/'false', not 1/0 (bool-before-int)
check("bool_true",  json.dumps(True) == 'true',   json.dumps(True))
check("bool_false", json.dumps(False) == 'false', json.dumps(False))

# 2. IntEnum emits int value, not repr
check("intenum",    json.dumps(IE.X) == '1',      json.dumps(IE.X))

# 3. str subclass
check("str_subclass", json.dumps(SS("x")) == '"x"', json.dumps(SS("x")))

# 4. list subclass with overridden __iter__ honors the override
check("list_subclass_iter",
      json.dumps(LSIter([1, 2, 3])) == '[3, 2, 1]',
      json.dumps(LSIter([1, 2, 3])))

# 5. dict subclass with overridden items() honors the override
check("dict_subclass_items",
      json.dumps(DS()) == '{"z": 1, "a": 2}',
      json.dumps(DS()))

# 6. signed zero
check("signed_zero_dumps", json.dumps(-0.0) == "-0.0", json.dumps(-0.0))
check("signed_zero_roundtrip",
      math.copysign(1, json.loads(json.dumps(-0.0))) == -1.0)

# 7. big int (no silent int64 truncation)
big = int("1" * 500)
check("big_int_roundtrip", json.loads("1" * 500) == big)

# 8. circular reference raises ValueError (not RecursionError, not segfault)
a = []
a.append(a)
try:
    json.dumps(a)
    check("circular_raises", False, "did not raise")
except ValueError:
    check("circular_raises", True)
except Exception as exc:
    check("circular_raises", False, f"raised {type(exc).__name__}")

# 9. object_pairs_hook honored
check("pairs_hook",
      json.loads('{"z":1,"a":2}', object_pairs_hook=list) == [('z', 1), ('a', 2)])

# 10. lone surrogate preserved on loads
check("lone_surrogate_loads",
      json.loads('"\\ud83d"') == '\ud83d')

# 11. lone surrogate preserved on dumps ensure_ascii=False
check("lone_surrogate_dumps_false",
      json.dumps('\ud83d', ensure_ascii=False) == '"\ud83d"')

# 12. control characters always escaped
check("control_chars_ascii",
      json.dumps("a\x00b\x01\x1fc") == '"a\\u0000b\\u0001\\u001fc"')
check("control_chars_nonascii",
      json.dumps("a\x00b\x01\x1fc", ensure_ascii=False)
          == '"a\\u0000b\\u0001\\u001fc"')

# 13. allow_nan semantics
check("nan_allowed", json.dumps(float('nan')) == 'NaN')
check("inf_allowed", json.dumps(float('inf')) == 'Infinity')
check("ninf_allowed", json.dumps(float('-inf')) == '-Infinity')
try:
    json.dumps(float('nan'), allow_nan=False)
    check("nan_rejected", False, "did not raise")
except ValueError:
    check("nan_rejected", True)

# 14. surrogate pair encoding under ensure_ascii=True
check("surrogate_pair_encode",
      json.dumps("\U0001d120") == '"\\ud834\\udd20"')

# 15. default() hook for unknown types
class E(json.JSONEncoder):
    def default(self, o):
        return "X"
check("default_hook", E().encode(object()) == '"X"')

# 16. sort_keys with int keys (coerce then compare as str? Actually it's as str)
# Python json sorts the string-coerced keys; 1 < 2 works for both int and str
check("sort_keys_int",
      json.dumps({2: 'a', 1: 'b'}, sort_keys=True) == '{"1": "b", "2": "a"}')

# 17. dict insertion order preserved on loads
check("load_order",
      list(json.loads('{"z":1,"a":2,"m":3}')) == ['z', 'a', 'm'])

# 18. parse_float=Decimal still works (non-default hook)
import decimal
check("parse_float_decimal",
      json.loads("[1.5]", parse_float=decimal.Decimal) == [decimal.Decimal("1.5")])

# 19. Reject trailing comma / unquoted keys
for bad in ('{a:1}', "'x'", '[1,]', '/*c*/1', 'undefined', '0x10'):
    try:
        json.loads(bad)
        check(f"reject_{bad!r}", False, "accepted")
    except json.JSONDecodeError:
        check(f"reject_{bad!r}", True)


print()
if failures:
    print(f"FAILED {len(failures)} checks: {', '.join(failures)}")
    sys.exit(1)
print("all guardrails passed")
