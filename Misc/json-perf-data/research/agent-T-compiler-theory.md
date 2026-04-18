# Agent T — Compiler-theoretic review of CPython's `json` encoder/decoder

I read `Modules/_json.c` in full, the two Python layers, and cross-checked what 3.15's adaptive interpreter already specializes (`Python/specialize.c` has 17 `BINARY_SUBSCR_*` / `LOAD_ATTR_*` / `FOR_ITER_*` families). The headline finding: the C encoder has already done a lot of the peephole work (`indent_cache`, `fast_encode` function pointer, `{}`/`[]` fast paths, integer-tp_repr shortcut, and `_PyUnicodeWriter` to avoid heap allocations per chunk). The remaining wins cluster around **partial evaluation of the encoder config** and **SIMD-style string scanning** — everything else is small or already done.

## 1. Peephole / keyhole optimization

**Already exploited?** Partially. `Modules/_json.c:1362-1422` (`create_indent_cache` / `update_indent_cache`) is textbook keyhole: it fuses `item_separator + '\n' + indent*k` into one precomputed PyUnicode and hands it back from `get_item_separator`. That collapses the dict-hot-path from 3 writer calls to 1 when indenting.

**What's left:** the non-indented dict path does **four** writer calls per k/v pair: `item_separator`, `encoder_write_string(key)`, `key_separator`, recurse-value (`_json.c:1715-1731`). `item_separator` and `key_separator` never change per encoder. We can fuse the leading `,"` (between items: `", "` + `"`) and the trailing `": "` into precomputed single `PyUnicodeWriter_WriteASCII` calls when both separators are ASCII (overwhelmingly the common case). Concretely: at encoder construction cache UTF-8 `const char*` buffers for `item_sep_plus_quote` and `close_quote_plus_key_sep`; replace the 2-4 `WriteStr` calls with `WriteASCII` (no refcount traffic, no `PyUnicode_Check`).

**Magnitude on `json.dumps({"k1":1,"k2":2,...})`:** each `PyUnicodeWriter_WriteStr` is ~20 ns of overhead (kind check + memcpy dispatch) vs ~5 ns for `WriteASCII` with a compile-time-known length. For a 10-key dict that's ~40 writer calls collapsed to ~20. Probably **3–5 %** of dumps time.

## 2. Partial evaluation / specialization of the Encoder

**Already exploited?** Barely. There's exactly one residual: `fast_encode` is a function pointer filled in at `encoder_new` (`_json.c:1346-1356`) by residualizing on whether `encoder is c_encode_basestring[_ascii]`. Everything else — `indent != Py_None`, `sort_keys`, `skipkeys`, `allow_nan`, `markers != Py_None` — is re-tested on every recursive call in `encoder_listencode_obj`, `encoder_listencode_dict`, and `encoder_encode_key_value`.

**Win:** this is the single biggest lens. The five booleans (`indent/none`, `sort_keys`, `skipkeys`, `check_circular`, `allow_nan`) produce 32 residual specializations, but in practice **one** dominates: `indent=None, sort_keys=False, skipkeys=False, check_circular=True, allow_nan=True` — the default `json.dumps`. Specialize that at encoder-construction time.

**Concrete proposal:** generate the three encoder functions from a macro templated on config flags (X-macro pattern), as CPython already does for `_PyEval_EvalFrameDefault` computed-gotos. At `encoder_new` (`_json.c:1358`), set a second function pointer `s->listencode_obj = listencode_obj_default` vs `listencode_obj_generic`. The default variant:
- drops the `s->indent != Py_None` check in `encoder_listencode_dict:1832,1872,1975` (4 sites, always false)
- drops `s->markers != Py_None` branches (`_json.c:1811, 1931` etc.) entirely when `check_circular=False`; inlines them without the `PyLong_FromVoidPtr` + `PyDict_Contains` ping-pong when `True`
- drops `s->sort_keys || !PyAnyDict_CheckExact(dct)` branch when `sort_keys=False` *and* the type test can be lifted

Treat this as the analogue of `LOAD_ATTR_INSTANCE_VALUE`: the interpreter caches type-version and specializes; here the "type-version" is the Encoder config, which never changes after construction.

**Magnitude:** Each recursion through `encoder_listencode_obj` currently costs ~6 branches for these flags, all predicted-not-taken but still fetching `s->indent`, `s->markers`. For small-dict dumps (the SO benchmark), this is **5–8 %**.

## 3. Register allocation / escape analysis

**Already exploited?** Largely yes. `_PyUnicodeWriter` already gives us a stack-ish buffer; `PySequence_Fast` + `PySequence_Fast_GET_ITEM` avoids creating an iterator object; integer fast-path (`_json.c:1590-1593`) uses `PyUnicodeWriter_WriteRepr` without a `PyObject*` round-trip for the repr's storage. The sorted-keys path (`_json.c:1840`) does allocate a list via `PyMapping_Items`, but only when `sort_keys=True` or for non-dict mappings — not on the hot path.

**What's left — small and honest:** `encoder_listencode_dict` always allocates an `ident = PyLong_FromVoidPtr(dct)` (`_json.c:1813`) when `markers != Py_None`, even when the dict ends up not being circular — i.e. always. That's a small-int-range allocation we could stack-allocate by using a pointer-keyed hashset (open-addressing, `uintptr_t` keys) instead of `markers` being a `PyDict`. This is exactly the escape-analysis pattern Java HotSpot's EA would identify: `ident` never escapes the frame.

**Concrete proposal:** at `Modules/_json.c:1813, 1933, 1623`, replace `PyLong_FromVoidPtr + PyDict_Contains + PyDict_SetItem + PyDict_DelItem` with a C-level `_PyHashSet_Void*` using stack storage for ≤16 entries and heap spill after. Interface change kept internal.

**Magnitude:** two `PyLong_FromVoidPtr` (heap) + three dict ops per container. For a small dict with two nested dicts, roughly **2–4 %**.

## 4. Grammar/lexer theory for the decoder

**Already exploited?** No — `scan_once_unicode` is recursive descent, and `scanstring_unicode` (`_json.c:498-515`) is already a tight char-at-a-time loop. Literals `true`/`false`/`null` are matched by `PyUnicode_ReadChar` sequences (not shown above but in the scanner dispatch).

**Win:** modest. A DFA/table-driven scanner pays off most when you have many tokens; JSON has 7 terminals. Where a table helps is **number parsing** — the current code scans [0-9.eE+-] in a hand loop then defers to `PyFloat_FromString`. A branchless classifier table (`uint8_t char_class[256]`) lets you detect end-of-number in a tight loop with one load + one compare per byte.

**Concrete proposal:** replace the sign/digit/frac/exp state-machine in `_match_number_unicode` (search for number-scan in `_json.c`) with a 256-entry `char_class[]` table keyed by ASCII. This is literally Aho/Sethi/Ullman §3.8 table-driven scanner. For `true`/`false`/`null`, current code already does what a DFA would — a 4/5-byte compare — so no change needed.

**Magnitude:** decoder-side, not encoder. For `json.loads("[1,2,3,...]")` integer-heavy workloads, **1–3 %**. Not interesting for encoder work.

## 5. Strength reduction in the ASCII-escape loop

**Already exploited?** No. `ascii_escape_size` (`_json.c:161-191`) and the main encode loop at `_json.c:208-217` walk character-by-character with `PyUnicode_READ` and `S_CHAR(c)` — a per-byte 4-way conjunction. This is the single biggest remaining bottleneck for string-heavy JSON (the common case: dict keys, string values).

**Win: large.** For 1-BYTE_KIND strings (Latin-1 / pure ASCII keys — which is the overwhelmingly common case for Python dict keys), we can scan with SIMD-width `memchr`-style "first byte in class" using the classic SWAR trick: a 64-bit word check for `< 0x20 | == '"' | == '\\' | >= 0x7f`. On the common no-escape path, this lets us size-check an entire string with ~1 cycle/byte instead of ~4.

**Concrete proposal:** in `ascii_escape_size` (`_json.c:161`) and `write_escaped_ascii` (`_json.c:240-276`), add a `kind == PyUnicode_1BYTE_KIND` fast path that does a SWAR word scan (`haszero`/Mycroft trick) — or use the `memchr` family applied repeatedly against each escape-needing byte when the builtin is well-inlined, but SWAR is cleaner. If the scan finishes with no escape-needing byte found, take the existing "no escape" branch (`_json.c:256`) directly without having ever walked the string twice.

**Magnitude:** the encoder currently walks most strings twice (once in `ascii_escape_size`, once in the actual write). A SWAR scan collapses the first pass to ~1/8 the cost and lets the second pass be a `memcpy`. For a dict of `{str: int}`, strings are half the bytes and most of the work: **10–20 %** on dumps, easily the biggest single win here. This is the same technique simdjson uses (scalar fallback version).

## 6. Hoisting loop invariants

**Already exploited?** Moderately. `encoder_listencode_dict` hoists `separator = s->item_separator` (`_json.c:1831`) into a local before the iteration loop. Good.

**What's left:** `encoder_listencode_obj` re-dereferences `s->indent != Py_None`, `s->markers != Py_None` on every recursive call even though neither can change mid-encode. Same for `s->fast_encode` inside `encoder_write_string` (`_json.c:1542`). These are one-load-per-call, but the call count is high.

**Concrete proposal:** at the top of `encoder_call` (`_json.c:1448`), copy `s->indent`, `s->markers`, `s->sort_keys`, `s->fast_encode` into local `const` variables and thread them through the recursion as function parameters (or via a small `EncodeCtx` stack struct passed by const pointer). The compiler currently cannot hoist these loads because `PyObject_CallOneArg(s->defaultfn, ...)` (`_json.c:1638`) could alias `s`.

**Magnitude:** subsumed by lens #2 if you do partial-eval properly. Standalone: **1–2 %**.

## Summary and priorities

Ranked by estimated payoff for the default `json.dumps({...})` call:

| # | Lens | Est. win | Effort |
|---|------|----------|--------|
| 5 | SWAR ASCII-escape scan | 10–20 % | medium (SWAR or target-specific SIMD) |
| 2 | Partial-eval encoder on config | 5–8 % | medium (X-macro template) |
| 1 | Fuse separator + quote writes | 3–5 % | easy |
| 3 | Stack hashset for circular markers | 2–4 % | easy-medium |
| 6 | Hoist config into locals | 1–2 % (subsumed by #2) | easy |
| 4 | Table-driven number scanner | 1–3 % (decoder-only) | easy |

Compared with the bytecode-specialization precedent: `LOAD_ATTR_INSTANCE_VALUE` gives ~5–10 % on attribute-heavy code by avoiding dict lookups that the compiler can prove redundant once type-version is cached. Lens #2 here is a **structurally identical argument** — the Encoder's config is a type-version that never changes — and deserves the same treatment. Lens #5 is the one that might get you past 10 % single-handed; everything else is low single digits.

File references: `Modules/_json.c` lines 161-276 (escape loops, lens 5), 1346-1356 (existing fast_encode residual, lens 2), 1569-1667 (`encoder_listencode_obj`, lens 2/6), 1670-1736 (`encoder_encode_key_value`, lens 1), 1798-1887 (`encoder_listencode_dict`, lens 1/3), 1362-1422 (existing indent peephole, lens 1).
