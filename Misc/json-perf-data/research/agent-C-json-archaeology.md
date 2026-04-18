# Agent C — `Modules/_json.c` optimization opportunities (CPython 3.15)

Ranked by expected impact on realistic workloads (deep/wide dicts, lots of short ASCII strings, many floats/ints). Line numbers refer to the `marshal-safe-cycle-design` branch checkout.

## 1. Two-pass `escape_size` + `escape_unicode_and_size` walks every string twice  **[L]**
**Location:** `Modules/_json.c:161-307`, consumed by `write_escaped_ascii` (241-276) and `write_escaped_unicode` (387-419), in every call path for string values and dict keys via `encoder_write_string` (1537-1557).

**Current shape:**
```c
Py_ssize_t output_size = ascii_escape_size(input, kind, input_chars);
...
if (output_size == input_chars + 2) {  /* no-escape fast path */
    ...WriteASCII(writer, input, input_chars)...
}
PyObject *rval = ascii_escape_unicode_and_size(input, kind, input_chars, output_size);
```
`ascii_escape_size` / `escape_size` do a full `PyUnicode_READ` per char just to decide whether any escaping is needed, and to compute the exact output length. The second pass then does the same scan again to actually emit.

**Proposed change:** Replace the sizing pass with a `memchr`-powered "find first escape-needing char" for the 1-byte case (the vast majority of JSON string traffic). For ASCII/Latin-1 input use a 256-bit bitmap to classify each byte in one load + test; bail out to the slow encoder only when we hit one. When the whole string is clean (`needle == NULL`), skip the allocation entirely and write the input straight to the writer with two quote chars — this is already the payoff branch, but it's currently reached only after a second linear scan. For 2-/4-byte kinds, fold the size computation into the emit loop by using `_PyUnicodeWriter_Prepare` with a generous initial estimate (`input_chars * 2 + 2`) and shrink on finish.

**Estimated impact:** L. String escaping dominates ASCII-heavy JSON encoding; a single-pass SWAR/`memchr` scan on the common "no escapes needed" path should cut encode time 10-20% on string-heavy payloads. Validation: `json.dumps` on Twitter-sample / GitHub-event datasets.

**Risk:** Low. Control-character handling (`c <= 0x1f`) and the `'\\'`, `'"'` boundary must be in the scanner bitmap. `ensure_ascii=True` additionally needs any `c > 0x7e`.

## 2. Exact-type fast dispatch in `encoder_listencode_obj`  **[M]**
**Location:** `Modules/_json.c:1568-1667`.

**Current shape:**
```c
else if (PyUnicode_Check(obj)) { ... }
else if (PyLong_Check(obj)) {
    if (PyLong_CheckExact(obj)) { return PyUnicodeWriter_WriteRepr(writer, obj); }
    ...
}
else if (PyFloat_Check(obj)) { ... }
else if (PyList_Check(obj) || PyTuple_Check(obj)) { ... }
else if (PyAnyDict_Check(obj)) { ... }
```
Every dispatch walks the MRO via `Py_TYPE(obj)` subclass checks before discovering the type is the exact builtin. For well-typed payloads (the 99% case) we pay 3-4 `PyType_IsSubtype` inclusion walks before landing in dict/list.

**Proposed change:** Lift a single `PyTypeObject *tp = Py_TYPE(obj);` and do identity checks first: `tp == &PyUnicode_Type`, `tp == &PyDict_Type`, `tp == &PyList_Type`, `tp == &PyLong_Type`, `tp == &PyFloat_Type`, `tp == &PyTuple_Type`. Fall through to the existing subclass-aware chain only on miss. Order by expected frequency (string, dict, list, long, float).

**Estimated impact:** M (2-5%). Measurable on deep structures where this function is hit millions of times; hotter with free-threading where `Py_TYPE` aliases less well.

**Risk:** None for correctness — the exact-type branches are a pure subset. Must preserve the existing subclass branches unchanged.

## 3. Per-dict `PyMapping_Items` + `PyList_Sort` allocates a full list even for exact `dict` when `sort_keys=True`  **[M]**
**Location:** `Modules/_json.c:1839-1855`.

**Current shape:**
```c
if (s->sort_keys || !PyAnyDict_CheckExact(dct)) {
    PyObject *items = PyMapping_Items(dct);
    if (items == NULL || (s->sort_keys && PyList_Sort(items) < 0)) { ... }
    ...
}
```
For exact dicts with `sort_keys=True` we build a list of 2-tuples (two allocations per entry) then sort it. We could iterate dict keys into a single flat array, sort the key array via `PyList_Sort`, then use `PyDict_GetItemWithError` in the emit loop — or better, pull `(key, value)` pairs directly from the dict's internal table and sort a `PyObject*[]` of keys, emitting values via the dict's `ma_values` slot.

**Proposed change:** For `PyDict_CheckExact(dct) && s->sort_keys`, allocate a `PyObject*` array of size `PyDict_GET_SIZE(dct)`, populate via `PyDict_Next`, sort with `PyObject_RichCompareBool` (same comparator as `list.sort`), and emit. Skip the 2-tuple boxing entirely. When `sort_keys=True` is common (pretty-printed config/audit JSON), this is a real win.

**Estimated impact:** M (2-6%) on `sort_keys=True` workloads; zero effect without it.

**Risk:** Must preserve the user-observable sort order — `list.sort` uses `PyObject_RichCompareBool(a, b, Py_LT)` stably; matching that is required. Keys that raise during comparison must propagate the same error.

## 4. Float formatting goes through `PyFloat_Type.tp_repr` + `_steal_accumulate`  **[M]**
**Location:** `Modules/_json.c:1510-1534`, `1599-1604`.

**Current shape:**
```c
return PyFloat_Type.tp_repr(obj);
...
PyObject *encoded = encoder_encode_float(s, obj);
...
return _steal_accumulate(writer, encoded);
```
Every finite float builds a brand-new `PyUnicode` object (1-byte ASCII, typically ≤24 chars), then `_PyUnicodeWriter_WriteStr` copies it into the writer, then we `Py_DECREF` it. The `repr` path itself calls `PyOS_double_to_string` internally, so the `PyUnicode` allocation is a pure middleman.

**Proposed change:** Call `PyOS_double_to_string(d, 'r', 0, Py_DTSF_ADD_DOT_0, NULL)` directly, then `PyUnicodeWriter_WriteUTF8(writer, buf, len)` (or WriteASCII), and `PyMem_Free(buf)`. No temp `PyUnicode`. Same approach for the `Infinity` / `-Infinity` / `NaN` strings — emit via `WriteASCII` directly instead of `PyUnicode_FromString` followed by `_steal_accumulate`.

**Estimated impact:** M (3-6%) on float-heavy payloads (numeric arrays, telemetry). Negligible for string-heavy.

**Risk:** Must preserve the exact repr format — Python's float repr uses the shortest round-trip; `Py_DTSF_ADD_DOT_0` with `'r'` format matches it. Pin down with existing test suite (`test_json.test_floats`).

## 5. Integer formatting allocates then copies  **[M]**
**Location:** `Modules/_json.c:1589-1597`, dict key path `1689-1691`.

**Current shape:**
```c
if (PyLong_CheckExact(obj)) {
    return PyUnicodeWriter_WriteRepr(writer, obj);
}
PyObject *encoded = PyLong_Type.tp_repr(obj);
...
return _steal_accumulate(writer, encoded);
```
`PyUnicodeWriter_WriteRepr` is already good for the exact path (it uses `_PyLong_FormatWriter` internally in modern CPython — check; if it falls back to `repr()` + copy, route to `_PyLong_FormatWriter` explicitly). In `encoder_encode_key_value` the non-exact `PyLong_Type.tp_repr` still allocates; force the exact-type check first and call `_PyLong_FormatWriter(writer, key, 10, 0)` directly.

**Proposed change:** Confirm `PyUnicodeWriter_WriteRepr` delegates to `_PyLong_FormatWriter` for longs. If not, add a direct call. Apply the same in the key path (line 1689) with exact-type gating.

**Estimated impact:** S-M. Small for normal workloads, bigger if the ints are large (multi-digit longs reallocate).

**Risk:** None on exact type. Subclasses must keep the `tp_repr` path for `__repr__` overrides.

## 6. `scanstring_unicode` inner hot loop per-char-reads with `PyUnicode_READ`  **[M]**
**Location:** `Modules/_json.c:498-515`.

**Current shape:**
```c
for (next = end; next < len; next++) {
    d = PyUnicode_READ(kind, buf, next);
    if (d == '"' || d == '\\') break;
    if (d <= 0x1f && strict) { raise_errmsg(...); goto bail; }
}
```
`PyUnicode_READ` is a macro that switches on `kind` every iteration. For the dominant 1-byte-kind case, the compiler can't hoist the switch cleanly across function boundaries. Use `memchr`-style SWAR: for 1-byte kind, mask test `0x22` / `0x5c` / `<=0x1f` using a precomputed bitmap, 8 bytes at a time with bithacks, or delegate to a dedicated `scan_string_ucs1` that uses a raw `const uint8_t *` pointer.

**Proposed change:** Dispatch on `kind` once at function entry and specialize the scan into three flat loops (`ucs1`, `ucs2`, `ucs4`). For `ucs1`, use a 32-byte lookup table (or two AVX2 comparisons) to find the next interesting byte. `memchr` alone won't work (three targets), but a byte-bitmap `if (table[*p]) break;` vectorizes well and the compiler can auto-vectorize.

**Estimated impact:** M (3-8%) for string-heavy JSON decoding. This is the hottest inner loop of `json.loads`.

**Risk:** Low, but the `strict=0` legacy path (accepts control chars) must remain correct; handle via a separate scan table.

## 7. `_match_number_unicode` uses per-char `PyUnicode_READ` and allocates a `PyBytes`  **[M]**
**Location:** `Modules/_json.c:984-1096`.

**Current shape:**
```c
numstr = PyBytes_FromStringAndSize(NULL, n);
...
for (i = 0; i < n; i++) {
    buf[i] = (char) PyUnicode_READ(kind, str, i + start);
}
if (is_float) rval = PyFloat_FromString(numstr);
else rval = PyLong_FromString(buf, NULL, 10);
```
Two issues: (a) repeated `PyUnicode_READ` with kind switch during scanning, and (b) allocating a `PyBytes` solely to have a C string for the parser. For the 1-byte-kind case we could pass `PyUnicode_1BYTE_DATA(pystr) + start` directly to `PyOS_string_to_double` / a local `_PyLong_FromStringAndBase` without any allocation.

**Proposed change:** Specialize on `kind == PyUnicode_1BYTE_KIND` (digits are ASCII so 1-byte input is by far the common case for realistic JSON — the whole document is usually ASCII). Use a stack buffer `char buf[64]` for the copy path when `n <= 64` (huge numbers are rare). Avoid `PyBytes` allocation entirely.

Also hoist the scanning loop specialization — eight `PyUnicode_READ(kind, str, idx)` per char of number is death by a thousand cuts.

**Estimated impact:** M (2-5%) on number-heavy payloads (analytics/metrics JSON).

**Risk:** Low. Stack buffer must fall back to heap for `n > 64`. Number syntax validation behavior unchanged.

## 8. `_parse_object_unicode` uses `PyDict_New` + `PyDict_SetItem` loop  **[S-M]**
**Location:** `Modules/_json.c:742-871`.

**Current shape:**
```c
rval = PyDict_New();
...
if (PyDict_SetItem(rval, key, val) < 0) goto bail;
```
For large JSON objects, the dict repeatedly resizes. Once the object is closed we know its size, but we could also peek at typical sizes via the comma count. Realistically the cleanest win is to use `_PyDict_NewPresized(4)` as a starting point and rely on doubling — but a more interesting opt: after finishing the object, if the final dict size is far below its allocated capacity, `_PyDict_SetItemKnownHash` with the already-computed key hash from the memo avoids rehashing every key.

**Proposed change:** (a) Use `_PyDict_NewPresized(8)` as a better starting point (reduces resize count). (b) Since every key is interned via `PyDict_SetDefaultRef(memo, key, key, ...)`, its hash is cached on the `PyUnicodeObject`; `PyDict_SetItem` already uses that, so no speedup there. Focus on (a) only.

**Estimated impact:** S (1-2%). The resize cost is O(log N); worth only on large objects.

**Risk:** None.

## 9. Marker dict manipulation allocates `PyLong` identity keys  **[S]**
**Location:** `Modules/_json.c:1620-1636` (and twice more in `encoder_listencode_list`, `encoder_listencode_dict`).

**Current shape:**
```c
ident = PyLong_FromVoidPtr(obj);
...
PyDict_Contains(s->markers, ident); PyDict_SetItem(s->markers, ident, obj); ...PyDict_DelItem(s->markers, ident);
```
Three dict ops + a `PyLong` allocation + free per container, even when `check_circular=True` is the default and `markers != None` but no cycle exists.

**Proposed change:** Use a C-level `PySet` of ids, or even better a small inline open-addressing hash set of `uintptr_t`. For the default case (no cycles), the happy path is one hash lookup + one insert + one remove without any Python-level allocation. Could also cache small pointer-hash slots stack-locally for shallow trees.

Alternative simpler win: use `_PyDict_SetItem_KnownHash` with a precomputed hash (just the pointer value shifted) to skip `PyLong`'s hash.

**Estimated impact:** S (1-3%). Hits every container entry, but `PyLong_FromVoidPtr` for small-int ptrs is fairly cheap; still, the triple dict op is not trivial.

**Risk:** Must preserve the `check_circular=False` path (markers is `None`) and the error reporting behavior.

## 10. `encoder_listencode_list` always calls `PySequence_Fast`, even on exact list/tuple  **[S]**
**Location:** `Modules/_json.c:1921-1930`.

**Current shape:**
```c
s_fast = PySequence_Fast(seq, "encoder_listencode_list needs a sequence");
```
For exact list/tuple (the overwhelmingly common case, already filtered by `encoder_listencode_obj`), `PySequence_Fast` becomes a no-op ref-increment, but it still goes through a function call and a type check.

**Proposed change:** When caller has confirmed `PyList_CheckExact(obj) || PyTuple_CheckExact(obj)`, skip the `PySequence_Fast` round-trip and go straight to `PyList_GET_ITEM` / `PyTuple_GET_ITEM` via two specialized paths. Inline helper templates or fall-through branch.

**Estimated impact:** S (<2%). Pure function-call overhead reduction.

**Risk:** None; the generic path stays for subclasses.

## 11. `PyUnicodeWriter_Create(0)` never pre-sizes  **[S]**
**Location:** `Modules/_json.c:1460` (encoder entrypoint), `532` (scanstring).

**Current shape:**
```c
PyUnicodeWriter *writer = PyUnicodeWriter_Create(0);
```
Starting from 0 forces several reallocations on any real payload. The encoder doesn't know the final size, but we can take a cheap upper bound — for `dumps(obj)` we could sample: if `obj` is dict, `sizeof * PyDict_GET_SIZE * 16`; if list, similar.

**Proposed change:** In `encoder_call` (line 1460), pass a size hint based on top-level container size: `PyDict_GET_SIZE(obj) * 24` or `PySequence_Length(obj) * 8`. For scanstring use `end - begin` — we're reading back the string and output is almost always within 1.5x input, so `end - begin` is tight.

**Estimated impact:** S (1-2%). Writer allocator is already amortized reasonably; this trims the first-few-reallocations penalty.

**Risk:** None — just a hint.

## 12. `_encoded_const` does 3 pointer compares per encode of None/True/False  **[S]**
**Location:** `Modules/_json.c:1577-1585` and `1491-1507`.

The `encoder_listencode_obj` function already tests `obj == Py_None/True/False` directly, so this is fine. But in `encoder_encode_key_value` (dict key path), we hit `_encoded_const` again — a duplicate branch. Minor.

**Proposed change:** Not worth pursuing independently; fold it into work on opportunity #2.

**Estimated impact:** S. Skip.

## 13. `write_escaped_unicode` uses the deprecated `_PyUnicodeWriter_WriteStr` internal  **[S]**
**Location:** `Modules/_json.c:407`.

**Current shape:**
```c
if (_PyUnicodeWriter_WriteStr((_PyUnicodeWriter*)writer, pystr) < 0) { ... }
```
This uses the 3.14-deprecated internal (`_Py_DEPRECATED_EXTERNALLY`) specifically because the public `PyUnicodeWriter_WriteStr` runs `str(obj)` on subclasses (gh-148241). Not a speed concern, but this is a correctness-vs-speed accommodation — worth noting for a follow-up public API (`PyUnicodeWriter_WriteStrNoSubclass` or a flag).

**Estimated impact:** S. Symptom, not an optimization lever.

## Already-optimized / don't bother

- **Scanner `null`/`true`/`false`/constant dispatch (`scan_once_unicode`, 1126-1202):** Literal comparisons, already branch-friendly. Making this table-driven would save nothing on modern branch predictors.
- **`ascii_escape_unichar` (126-159):** Already a tight switch; table-driven won't help since the common case (`S_CHAR`) is handled before we get here. The hex-digit emission uses `Py_hexdigits`.
- **Indent cache (1372-1445):** Already memoizes newline+indent and separator+newline per depth; list-based memoization is fine.
- **`fast_encode` function-pointer in `PyEncoderObject` (64, 1348-1356):** Cached at encoder create time; dispatch is a single indirect call. Good design.
- **Empty-container fast paths:** `"{}"` (1806-1809) and `"[]"` (1926-1929) are already short-circuited.
- **Dict iteration under `Py_BEGIN_CRITICAL_SECTION`:** Necessary for free-threading correctness, cheap on default build, can't be removed.
- **Key memoization via `PyDict_SetDefaultRef` (789-792):** The `memo` dict already interns repeated keys so identical-key decode is fast. Pointless to change.
- **`_build_rval_index_tuple` / `_PyTuple_FromPairSteal` (453-468):** Already the fastest way to build a 2-tuple without GIL dance.
- **`encoder_call` tuple wrapping of result (1485-1487):** The one-element tuple exists for backward-compat with the Python iterencode path that expects a generator; can't be removed without API change.

## Order of attack if I were doing this

1. **(#1)** Single-pass escape scan with bit-table / `memchr` — the single largest lever for the encoder.
2. **(#6)** Kind-specialized string scan in the decoder — the corresponding lever for `loads`.
3. **(#2)** Exact-type fast dispatch in `encoder_listencode_obj` — cheap to implement, broad effect.
4. **(#4)** Direct `PyOS_double_to_string` → writer for floats.
5. **(#7)** Stack-buffer number parse without `PyBytes`.
6. **(#3)** `sort_keys` fast path without 2-tuple boxing.

Anything below #6 is under-2% individually and only worth bundling into a sweep once the big wins land — micro-optimizations compound, but don't chase them first.
