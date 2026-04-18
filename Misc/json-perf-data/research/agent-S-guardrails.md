# Agent S — json Optimization Guardrails

Diff every proposed change against this list. Any "fail" = do not ship without explicit ack from the reviewer. "Rule / Why / Check" per item.

## 1. RFC 8259 / ECMA-404 output compliance

### 1.1 Control chars must be escaped in string output
- **Rule**: Every code point in `U+0000..U+001F` must be emitted as `\"`, `\\`, `\b`, `\f`, `\n`, `\r`, `\t`, or `\u00XX`. `"` and `\` must be escaped. `/` MAY be emitted raw.
- **Why**: Raw controls produce invalid JSON that other parsers reject (and some treat as framing markers, a smuggling vector).
- **Check**: `json.dumps("a\x00b\x01\x1fc") == '"a\\u0000b\\u0001\\u001fc"'` under both `ensure_ascii=True` and `False`.

### 1.2 `ensure_ascii=False` still emits valid UTF-8-encodable `str`
- **Rule**: Output is a Python `str`. When the user later encodes it as UTF-8, it must round-trip to the original text (modulo escapes). Non-ASCII codepoints above `0x7f` pass through literally; they are NOT smuggled as raw bytes.
- **Why**: Optimizations that bypass the kind-aware `PyUnicode_READ` (e.g. memcpy of 1BYTE data when input is 2/4BYTE) corrupt output.
- **Check**: `json.dumps("\u00e9\u4e2d\U0001f600", ensure_ascii=False)` → `'"\u00e9\u4e2d\U0001f600"'` and `.encode('utf-8')` round-trips.

### 1.3 Surrogate pairs on ASCII escape
- **Rule**: Code points `>= 0x10000` with `ensure_ascii=True` emit a UTF-16 surrogate pair `\uD8xx\uDCxx`. Existing behavior in `ascii_escape_unichar` (`Modules/_json.c:142-149`).
- **Check**: `json.dumps("\U0001d120") == '"\\ud834\\udd20"'`.

### 1.4 Lone surrogates – preserve existing behavior, do not "fix"
- **Rule**: Python's json currently PRESERVES lone surrogates on both encode and decode. `dumps('\uD83D')` → `'"\\ud83d"'` (ascii) or `'"\ud83d"'` (no ascii). `loads('"\\udc0d"')` → `'\udc0d'`. This is locked in by `test_unicode.py` lines 74–84.
- **Why**: Changing to a replacement char or raising is a behavior break. A "validate UTF-8 on output" optimization that rejects lone surrogates is a breaking change.
- **Check**: Run `Lib/test/test_json/test_unicode.py::test_single_surrogate_{encode,decode}`.

## 2. Python-specific API contract

### 2.1 `cls=` subclass – hot paths MUST fall back
- **Rule**: If the user passes `cls=MyEncoder`, any subclass that overrides `default`, `encode`, `iterencode`, `JSONEncoder.default`, or on the decode side `JSONDecoder.decode`, `raw_decode`, `parse_object`, `parse_array`, `parse_string`, `scan_once`, must be honored. The C `make_encoder` fast path is already engaged only when the pure Python `JSONEncoder.iterencode` is used with `_one_shot=True`. Do not extend the C fast path to run when `type(self) is not JSONEncoder`.
- **Why**: Subclasses in the wild override `iterencode` for streaming, auditing, redaction. Silent bypass is a correctness break and an info-leak risk.
- **Check**: Subclass `JSONEncoder`, override `default` to record calls; encode `{MyObj()}`; verify override fires.

### 2.2 `JSONEncoder.default` is part of the public contract
- **Rule**: For any object that is not one of the exact built-ins or subclasses of them (str/int/float/bool/None/list/tuple/dict), `self.default(obj)` MUST be called. Do NOT skip it on exact type checks for unknown types.
- **Why**: This is the documented extension point (`Doc/library/json.rst`).
- **Check**: `class E(JSONEncoder): def default(self,o): return "X"` → `E().encode(object())` → `'"X"'`.

### 2.3 Decode-side hooks: `object_hook`, `object_pairs_hook`, `parse_float`, `parse_int`, `parse_constant`, `array_hook`, `strict`
- **Rule**: The scanner identity check `s->parse_float != (PyObject *)&PyFloat_Type` (and equivalent for `parse_int`) gates the fast native parse. Any optimization must preserve this gate. If the user provides a hook, it must be called with the raw numeric substring (for parse_float/int) or the exact constant string "NaN"/"Infinity"/"-Infinity" (for parse_constant). `object_pairs_hook` takes priority over `object_hook`.
- **Why**: People use `parse_float=decimal.Decimal` for financial data. Silent `float` coercion is a silent precision/correctness loss.
- **Check**: `json.loads("[1.5]", parse_float=Decimal) == [Decimal("1.5")]`; `json.loads("NaN", parse_constant=lambda s: s) == "NaN"`.

### 2.4 `sort_keys` / `indent` / `separators` / `skipkeys`
- **Rule**: `sort_keys=True` sorts by `key` before emission (`PyList_Sort` on an items list, which uses `<`). `skipkeys=True` skips non-(str/int/float/bool/None) keys silently; non-skipkeys path raises `TypeError`. `indent` semantics: `None` = compact; `int` = that many spaces; `str` = literal indent string. Default `separators` change based on `indent`: `(', ', ': ')` vs `(',', ': ')`.
- **Check**: `json.dumps({2:'a', 1:'b'}, sort_keys=True)` → `'{"1": "b", "2": "a"}'` (note: int keys coerced to str, sorted by int value before coercion).

### 2.5 Dict insertion order preservation (3.7+)
- **Rule**: Encoder iterates `dict` in insertion order unless `sort_keys=True`. Decoder returns a `dict` that preserves the insertion order of the keys as seen in the JSON input. Do NOT reorder for hashing/bucketing wins.
- **Check**: `list(json.loads('{"z":1,"a":2,"m":3}')) == ['z','a','m']`.

### 2.6 `check_circular=False` – documented escape hatch
- **Rule**: Promise is: "no markers dict, infinite recursion is the user's problem." An optimization may legitimately skip the markers dict when `check_circular=False`. When `check_circular=True` (default), markers MUST be maintained across every recursive descent into containers AND into `default()` returns.
- **Why**: Users who pass `check_circular=False` have asserted acyclicity. Users who keep the default rely on `ValueError("Circular reference detected")` rather than a RecursionError / SIGSEGV.
- **Check**: `a=[]; a.append(a); json.dumps(a)` → `ValueError`, not segfault, not RecursionError.

## 3. Security

### 3.1 Recursion bomb resistance
- **Rule**: Both encode and decode MUST call `_Py_EnterRecursiveCall` at each nesting level (already done at `Modules/_json.c:1132,1140,1606,1613,1644`). Optimizations that flatten recursion to a hand-rolled stack must enforce a depth bound and raise `RecursionError` (not crash, not consume unbounded memory).
- **Check**: `json.loads("[" * 100_000 + "]" * 100_000)` raises `RecursionError`, does not SIGSEGV. Same for `json.dumps` on a 100k-deep nested list.

### 3.2 Unbounded integer input
- **Rule**: `json.loads("1" + "0"*4300)` must parse by default (subject to `sys.get_int_max_str_digits()`). Do not introduce a silent truncation to int64. If you add a fast path for small ints, fall back to `PyLong_FromString` for long strings.
- **Check**: `json.loads("1" * 1000) == int("1"*1000)`.

### 3.3 User hooks can raise – error paths must not be reordered
- **Rule**: `object_hook`, `object_pairs_hook`, `parse_float`, `parse_int`, `parse_constant`, `default`, `array_hook` may raise arbitrary exceptions (including `KeyboardInterrupt`). Exceptions must propagate with no result materialization, no swallowing, no silent retry. `add_note`-style context augmentation (`_PyErr_FormatNote` in `Modules/_json.c`) is part of the contract — don't lose it.
- **Check**: `json.dumps({1: object()}, default=lambda o: (_ for _ in ()).throw(RuntimeError("x")))` propagates `RuntimeError`.

### 3.4 Be on the right side of parser CVEs
- **Rule**: No duplicate-key silent merging into a non-last-wins policy (last-wins is dict semantics and is fine; altering it is not). No accepting unquoted keys. No accepting single-quoted strings. No accepting trailing commas (already explicitly rejected, `Lib/json/decoder.py:210`). No accepting comments. No accepting `undefined`. No octal/hex integer literals. No multi-line strings. Any "permissive mode" must be an explicit opt-in, never a side effect of an optimization.
- **Check**: Each of `json.loads('{a:1}')`, `json.loads("'x'")`, `json.loads("[1,]")`, `json.loads("/*c*/1")`, `json.loads("undefined")`, `json.loads("0x10")` raises `JSONDecodeError`.

### 3.5 BOM handling
- **Rule**: Bytes input starting with UTF-16/32 BOM is auto-detected (`Lib/json/__init__.py:249-253`). Bytes starting with UTF-8 BOM is rejected. `str` input starting with `\ufeff` is rejected with a specific error message. Do not "helpfully" strip it.
- **Check**: `json.loads('\ufeff{}')` raises `JSONDecodeError` mentioning `utf-8-sig`.

## 4. Floating point

### 4.1 Shortest round-trip
- **Rule**: `json.dumps(f)` for finite `f` delegates to `PyFloat_Type.tp_repr` (`Modules/_json.c:1533`). This uses Python's dtoa to produce the shortest string that round-trips to the same double. Do not substitute `printf("%.17g")` or `snprintf("%.15f")` — both regress.
- **Check**: For every `f` in `[0.1, 1/3, 1e308, 2.2250738585072014e-308, sys.float_info.max]`: `float(json.dumps(f)) == f` and `len(json.dumps(f)) == len(repr(f))`.

### 4.2 `allow_nan` semantics
- **Rule**: `allow_nan=True` (default): `NaN`, `Infinity`, `-Infinity` are emitted as bare tokens (non-RFC, documented). `allow_nan=False`: emitting one raises `ValueError`. Fast path must check `isfinite` before calling `tp_repr`.
- **Check**: `json.dumps(float('nan'))=='NaN'`; `json.dumps(float('nan'), allow_nan=False)` raises `ValueError`.

### 4.3 Negative zero preserved
- **Rule**: `json.dumps(-0.0) == '-0.0'` and `json.loads('-0.0')` returns a float that compares equal to 0.0 but has negative sign bit.
- **Check**: `import math; math.copysign(1, json.loads(json.dumps(-0.0))) == -1.0`.

## 5. Unicode edge cases

### 5.1 NFC/NFD normalization — NONE
- **Rule**: Do not normalize. Bytes-identical Unicode passes through.
- **Check**: `s='\u00e9'; t='e\u0301'; json.loads(json.dumps(s))==s and json.loads(json.dumps(t))==t and s!=t`.

### 5.2 Decoder `\uXXXX` surrogate pair merging
- **Rule**: Existing behavior: a high-surrogate `\uDxxx` immediately followed by `\uDCxx` is combined to the astral code point. A high-surrogate followed by anything else is emitted as the lone surrogate. See `Modules/_json.c:600-629` and `Lib/json/decoder.py:120-125`. Preserve both branches.

## 6. Concurrency & re-entrancy

### 6.1 User code may mutate the container mid-encode
- **Rule**: `default`, `__iter__`, `items()`, `__hash__` of keys, `__lt__` used by `sort_keys` — all may run user Python that mutates the list/dict being iterated. The C encoder already defends via `Py_INCREF` on borrowed items (`_json.c:1750, 1782-1783, 1898`) and via `Py_BEGIN_CRITICAL_SECTION(_SEQUENCE_FAST)` on free-threading builds. Any optimization that replaces these with raw `PyList_GET_ITEM` borrowed loops without INCREF reintroduces gh-142831 / gh-145244.
- **Check**: Regression tests added for those bug numbers.

### 6.2 `check_circular` markers dict across user callbacks
- **Rule**: Markers are keyed by `id(obj)` (via `PyLong_FromVoidPtr`). Entry is inserted before recursing into contents / before calling `default`; entry is deleted on successful return. Error paths leak the entry but the dict dies with the encoder — acceptable. Do not add an entry without a matching delete on the success path.

## 7. Subinterpreter / free-threading

### 7.1 No new mutable module state
- **Rule**: Module is declared `Py_MOD_PER_INTERPRETER_GIL_SUPPORTED` and `Py_MOD_GIL_NOT_USED` (`_json.c:2082-2084`). New static mutable state (caches, interned dicts, lookup tables) breaks this. Read-only static tables (e.g. `Py_hexdigits`) are fine.
- **Check**: `python -X subinterpreters` or the existing free-threading CI smoke test.

### 7.2 Critical sections on containers
- **Rule**: Under `--disable-gil`, iteration over dict/list items needs the critical-section macros when borrowed refs are used. The existing pattern `Py_BEGIN_CRITICAL_SECTION(dct)` / `Py_BEGIN_CRITICAL_SECTION_SEQUENCE_FAST(seq)` must be preserved when the optimized loop still uses `PyDict_Next` or `PySequence_Fast_GET_ITEM` borrowed refs.

## 8. Exact-type fast paths — the golden rule

### 8.1 Rule
Use `Py_TYPE(obj) == &PyFoo_Type` (or `PyFoo_CheckExact`) to skip the generic path ONLY when ALL of the following hold:

1. The operation reads data via APIs that do not go through `tp_*` slots of the subclass (e.g. `PyUnicode_DATA`, `PyLong_AsLongLong`, `PyList_GET_ITEM`, `PyDict_Next`).
2. The operation does NOT call `repr()`, `str()`, `__iter__`, `__getitem__`, `keys()`, `items()`, `__eq__`, `__hash__`, or `__lt__` on the object (those can be overridden in subclasses).
3. For emission, you know the exact-type canonical form is correct JSON. `int.__repr__` for an IntEnum instance must emit the int value, not the enum name — so `PyLong_CheckExact` is safe, but `PyLong_Check` demands you call `PyLong_Type.tp_repr(obj)` explicitly rather than `PyObject_Repr` (already done at `_json.c:1594`).
4. The Python fallback (`Lib/json/encoder.py`) uses `isinstance`, not `type() is` — so an exact-type C fast path must be semantically equivalent to running the subclass's overridden method *only when no override exists*. If in doubt: check `Py_TYPE(obj)->tp_repr == PyLong_Type.tp_repr` before shortcutting, or just call the base type's slot directly.

### 8.2 Counter-examples (DO NOT shortcut)

- **`dict` subclass with overridden `__iter__` / `keys` / `items`**: `OrderedDict`, `collections.Counter` with custom iteration, `defaultdict` with a factory that mutates during encode — you must go through `PyMapping_Items` (current code: `_json.c:1839` uses `PyAnyDict_CheckExact` gate). A naive `PyDict_Check` fast path breaks these.
- **`list` subclass with overridden `__iter__`**: same — current code uses `PySequence_Fast` which respects `__iter__`.
- **`str` subclass with overridden `__str__`/`__repr__`**: gh-148241 specifically fixed this. Do NOT call `PyUnicodeWriter_WriteStr` on a str subclass (which calls `str(obj)`); use the `_PyUnicodeWriter_WriteStr` lower-level variant or `PyUnicode_DATA` directly.
- **`int` subclass (IntEnum)**: `int.__repr__(IntEnum.FOO)` → `"1"`, but `repr(IntEnum.FOO)` → `"<FOO: 1>"`. Encoding the latter would produce invalid JSON. Always route through `PyLong_Type.tp_repr`, never `PyObject_Repr`.
- **`float` subclass**: same story as int.
- **`bool`**: `PyLong_Check(True)` is True. Always test `obj is Py_True / Py_False` BEFORE `PyLong_Check`, or the fast path emits `"1"` / `"0"` instead of `"true"` / `"false"`. Current code gets this right (`_json.c:1580-1585`); a reordering "optimization" silently breaks it.

### 8.3 Self-check battery
A single test module that every optimization must pass, combining the above:

```python
import json, enum, collections, decimal
class IE(enum.IntEnum): X = 1
class SS(str): pass
class LS(list):
    def __iter__(self): yield from reversed(super().__iter__().__self__)
class DS(dict):
    def items(self): return [('z', 1), ('a', 2)]
# golden assertions
assert json.dumps(True) == 'true'
assert json.dumps(IE.X) == '1'
assert json.dumps(SS("x")) == '"x"'
assert json.dumps(LS([1,2,3])) == '[3, 2, 1]'
assert json.dumps(DS()) == '{"z": 1, "a": 2}'
assert json.loads(json.dumps(-0.0)) == 0.0
assert json.loads("1" * 500) == int("1"*500)
a=[]; a.append(a)
try: json.dumps(a); assert False
except ValueError: pass
assert json.loads('{"z":1,"a":2}', object_pairs_hook=list) == [('z',1),('a',2)]
assert json.loads('"\\ud83d"') == '\ud83d'
assert json.dumps('\ud83d', ensure_ascii=False) == '"\ud83d"'
```

Any patch that fails any assertion here is rejected without further review.
