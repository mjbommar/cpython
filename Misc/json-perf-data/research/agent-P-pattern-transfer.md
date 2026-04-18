# Agent P — Pattern transfer from marshal / pickle / logging to json

## Pattern catalog

**P1 — Replace a `PyList`-backed accumulator with a raw `PyObject **` / `T *` growable array.**
Marshal Exp 1: `RFILE.refs` went from a Python list to `PyObject **refs; refs_len; refs_cap;`. Dominant single win of the whole marshal push (−22.6% on `small_tuple` loads; −24% combined). Worked because the outer dispatch called `PyList_Append` once per element — generic-list machinery overhead drowned the work the new code needed to do.

**P2 — Tagged-pointer / single-allocation state.**
Marshal Exp 2: encoded a per-slot state byte in the low bits of the stored pointer, eliminating a parallel `ref_states` byte array. −5.9% on top of Exp 1. Worked because the "second structure" was touched in lockstep with the first; collapsing them halved cache traffic.

**P3 — Match the reference implementation's dispatch order (atomics-first).**
Pickle F1: reordered pure-Python `save()` so `str`/`int`/`None`/`bool`/`float` are identity-tested *before* the memo lookup and *before* `reducer_override`, mirroring `Modules/_pickle.c::save()`. −7.8 to −30.4% depending on workload (biggest single pickle win). Str first, then non-memoized atomics, then memo check for everything else.

**P4 — Exact-type fast path that skips the generic iterator/batching layer.**
Pickle Exp 4: `_batch_appends_exact` / `_batch_setitems_exact` gated on `type(obj) is list` / `type(obj) is dict`, using a slice snapshot instead of `itertools.batched(...)` + `enumerate()`. −17 to −22% on nested workloads. Worked because generic batching allocates a tuple + enumerate object per batch; exact types can loop the container directly.

**P5 — Precomputed small-value byte/string cache.**
Pickle F4: module-level tuple of 256 `BININT1 + bytes([i])` precomputed at import. −9.9% on int-heavy workload. One-time ~50 KB memory cost; bounded payoff but zero downside.

**P6 — Inline a method call whose common-case body is trivial; call the method only when a cheap precondition fires.**
Pickle Exp D: replaced `self.framer.commit_frame()` at top of `save()` with two attribute loads + a condition, falling into the real method only when a frame is actually due. Consistent −5 to −10% because the replaced call was invoked per-value on every `save`.

**P7 — Inline MEMOIZE-style single-byte emission into the caller.**
Pickle F2: `memoize()` stopped going through `self.write(self.put(idx))` on proto ≥ 4 and wrote `MEMOIZE` directly. −1 to −2% consistently. Same shape as P6 but for the write path.

**P8 — Force `static inline` on tiny helpers.**
Marshal Exp 7: annotating six one-line `r_ref_*` helpers with `static inline` unlocked −3% free. Compilers often decline to inline multi-caller `static` functions.

**P9 — Pure-function result cache keyed on immutable input.**
Logging Phase 1: module-level `_internal_frame_cache` (keyed on `co_filename`) and `_pathname_to_fields_cache` (keyed on `pathname`). −10% end-to-end on R1. Safe because the cached results are deterministic from immutable keys; worst-case size is bounded by count of source files seen.

**P10 — Snapshot immutable module state at install; stop re-looking it up.**
Logging Phase 1: `_main_thread_ident` / `_main_thread_name` captured once at import. Logging Phase 1 #4: `_levelname_cache` snapshot of `_nameToLevel` rebuilt only on `addLevelName`. Eliminates a lock + dict lookup from every LogRecord create.

**P11 — Preallocate typed fast-path structure at `__init__` instead of computing it per call.**
Logging L2 discovery: `Logger.isEnabledFor._cache` already did exactly this (pre-existing). Pattern: if the same boolean / small struct is recomputed every call and only invalidates on config events, cache + epoch-bump.

## Transfer map

The json C accelerator is the default path; the pure-Python path matters for subclasses of `JSONEncoder` (whoever overrides `default()` or `iterencode()` ends up in pure Python) and as a correctness reference. Profile hotspots in any JSON-emitting workload cluster into: (a) per-value dispatch in the encoder, (b) string escape size-then-emit passes, (c) string scan in the decoder, (d) key repetition / interning in the decoder, (e) `PyList_Append` growth in both decoder array/object builds.

**T1 — `_parse_array_unicode` uses `PyList_Append` per element.** `Modules/_json.c:910`. Every JSON array element goes through a full PyList append, including the amortized-geometric-growth check. **Apply P1.** Maintain a raw `PyObject **vals; Py_ssize_t vals_len, vals_cap;` local; do `PyList_New(vals_len)` + `PyList_SET_ITEM` memcpy at the end, or use `_PyList_AppendTakeRef` where available. Same shape as marshal Exp 1. **Expected win: −10 to −20% on array-heavy JSON decode**, scaling with array length. Largest single decoder win available.

**T2 — `_parse_object_unicode` does `PyDict_SetItem` per pair even on fresh dicts.** `Modules/_json.c:821`. Use `_PyDict_SetItem_KnownHash` (the hash was computed by `PyDict_SetDefaultRef` at `:789` for memo interning) to avoid a second hash. Also: when `has_pairs_hook` is false and `s->object_hook == Py_None`, the common case, preallocate via `_PyDict_NewPresized` with an educated size guess after one pair has been seen (peek ahead for `,` vs `}` density is too invasive; instead presize to 8 on first non-empty pair, then the dict's own resize amortizes). **Win estimate: −3 to −8% on dict-heavy decode** (comparable to pickle F2's inline-MEMOIZE pattern P7).

**T3 — Key memo is per-`JSONDecoder`-instance.** `Lib/json/decoder.py:349` — every custom decoder (including `JSONDecoder()` freshly built for each `json.loads` call that passes *any* hook) gets `self.memo = {}`. This was already flagged in `Misc/cpython-perf-ideas.md` item #14. **Apply P9.** Add a bounded module-level LRU (or a size-capped dict with a simple eviction-on-insert-past-N rule; 4096 entries is ample and ~200 KB bounded). Keys like `"timestamp"`, `"level"`, `"msg"` are shared across 100% of log-ingest payloads. Keep the per-instance memo as a fallback for the hook path. **Win estimate: −5 to −15% on JSON-log ingestion**, straight analogue of logging `_pathname_to_fields_cache`. *This is the single highest-leverage pure-Python json change.*

**T4 — `encoder_listencode_obj` dispatch order does not match pickle's atomic-first order.** `Modules/_json.c:1577-1618`. Current order is fine for None/bool but `PyUnicode_Check(obj)` is checked *after* three pointer comparisons. `str` is by far the most common list/dict item in real JSON payloads. **Apply P3.** Reorder: `PyUnicode_Check` first, then `PyLong_Check` with `PyLong_CheckExact` fast path, then the `is Py_None/Py_True/Py_False` identity tests, then `PyFloat_Check`, then containers. Also worth a `Py_TYPE(obj) == &PyUnicode_Type` identity check before `PyUnicode_Check` (the check macro walks `tp_flags`). **Win estimate: −2 to −5% on string-heavy workloads**, smaller than pickle F1 because json's dispatch is already C-level (no memo, no reducer_override).

**T5 — `ascii_escape_size` walks the whole string; so does the subsequent `ascii_escape_unicode_and_size` loop.** `Modules/_json.c:162` + `:208`. Two full walks over every string even when no escaping is needed. The `output_size == input_chars + 2` branch at `:256` handles the no-escape case, but still after a full size pass. **Apply P4 analogue.** Fuse into a single pass: scan for the first escape-requiring char using `memchr`-style search across the `S_CHAR` mask; if none, write directly without a size pass. For ASCII 1BYTE strings this collapses to a `memchr` over `"` / `\` / control-byte mask. Existing `cpython-perf-ideas.md` already flagged "on our radar: `_json.c` string-scan via `memchr` and homogeneous-dict fast path". **Win estimate: −15 to −30% on short-ASCII-string-heavy encode** (dict keys especially). This is the encoder's equivalent of P4.

**T6 — `PyLong_FromVoidPtr` + `PyDict_SetItem` for circular markers every container.** `Modules/_json.c:1623, 1813, 1933`. Every list / dict / custom object allocates a PyLong ident and does two dict ops. For acyclic payloads (the 99% case) this is pure overhead. **Apply P11 + pickle Exp C pattern.** Skip marker bookkeeping when the container is a freshly-constructed `list` / `dict` / `tuple` from untrusted user code? Safer: introduce a "low-water mark" fast path — if `PyDict_GET_SIZE(s->markers) == 0` on entry and the container's refcount is 1 (fresh), skip the setitem/delitem pair and use a local-array mark stack instead. Complex; defer. **Cheaper win**: use `PyLong_FromSize_t((uintptr_t)obj >> 3)` and preallocate an int-cache for small id buckets. **Win estimate: −3 to −8% on container-heavy encode**, medium confidence.

**T7 — `_match_number_unicode` does a byte-copy loop + `PyLong_FromString`.** `Modules/_json.c:1085-1091`. For the overwhelmingly-common small-positive-int case, `PyLong_FromString` through a 10-char bytes object is a lot of machinery. **Apply P5.** Add a small-int fast path: if `idx - start <= 18` (fits in int64), parse into a `Py_ssize_t` inline and return `PyLong_FromSsize_t(v)`. For `v` in `[-128, 256]` CPython's small-int cache already dedups. **Win estimate: −10 to −25% on integer-heavy decode** (timestamps, array indices, IDs). Bounded payoff, zero downside.

**T8 — `_encoder_iterate_fast_seq_lock_held` pays `Py_INCREF`/`Py_DECREF` per element.** `Modules/_json.c:1894-1911`. The `Py_INCREF(obj)` around every element (to defend against user-code mutation) plus `PyUnicodeWriter_WriteStr(writer, separator)` for every `i > 0`. Apply a specialized `_encoder_iterate_exact_list_ints` / `_exact_list_strs` when all elements share a type — analogue of pickle F7 / the "homogeneous-list specialization" left on the table in pickle's "what we didn't try". A single type-check pre-pass on a short list can unlock a tight loop with no dispatch inside. **Win estimate: −8 to −15% on homogeneous numeric arrays** (numpy-source-shaped).

**T9 — Default encoder `iterencode` in pure Python is a closure factory.** `Lib/json/encoder.py:265`. When the C encoder is unavailable (subclass overrides `iterencode` or `default`), every call through `_make_iterencode` builds six nested closures. **Apply P6/P7.** Hoist the atomic dispatch into a single top-level `_iterencode` with prebound locals; pickle's pure-Python path gained this shape in Round 1. This path runs whenever a user does `class MyEncoder(JSONEncoder): def default(self, o): ...` which is common. **Win estimate: −15 to −25% on pure-Python encoder subclass path**, same shape as pickle Exp D + E combined.

**T10 — `py_scanstring` and `STRINGCHUNK` regex.** `Lib/json/decoder.py:54, 70`. Hits when a subclass overrides `parse_string`. Apply prebinding (pickle D pattern) + inline the `match.groups()` / `match.end()` calls as locals. Smaller win; include only if T1-T3 are being touched.

Ranking by confidence × magnitude: **T3 > T1 > T5 > T7 > T4 > T2 > T9 > T8 > T6 > T10**. T3, T1, T5 are the three headline picks.

## Anti-patterns to avoid

**A1 — Don't introduce a Python-level counter to replace a C-method call.**
Pickle F3: replacing `BytesIO.tell()` with a self-maintained `current_frame_size` int counter *regressed* every workload 3-5%. In json, the analogue would be: don't try to replace `PyUnicode_GET_LENGTH` / `PyUnicodeWriter_WriteStr`'s internal bookkeeping with Python-level tracking. The C path is already a direct C-method call on a C type.

**A2 — Don't re-specialize a codec Python already specializes.**
Pickle F5: adding an ASCII fast path via `.encode('ascii')` around `obj.isascii()` was flat because utf-8 codec already memcpys ASCII. In json this bites at `py_encode_basestring` — don't add an `isascii()` + `.encode('ascii')` front. Stay in the C encoder or use regex short-circuit. *However*, T5's `memchr` proposal operates at the unicode-scan level, not the codec level; that's orthogonal and safe.

**A3 — Don't try to beat `PyType_Lookup`'s type-attribute cache with hand-rolled `__dict__` probes.**
Pickle Exp B: hoisting `persistent_id` / `reducer_override` hook probes to `__init__` regressed 17-36%. In json the analogue is any attempt to cache `self.default is not JSONEncoder.default` or `self.indent is None` in a side-table — don't. The existing `_one_shot and c_make_encoder is not None` fast path at `Lib/json/encoder.py:253` already uses the right mechanism (check once at call time, dispatch to C). Leave it alone.

**A4 — Don't cross the Python↔C boundary just to shave C-level work.**
Logging Phase 2: C `findCaller` isolated +38% was eaten by tuple-construction overhead at the boundary; net +1.0%. In json this would be a wrong pattern for "port `JSONObject` pure-Python to a new C helper" — it's already in `_json.c`. It *is* the right pattern for extending the existing C module with more fast paths (T1, T5, T7), which never cross back to Python.

**A5 — Don't specialize for data shapes the bench doesn't exercise.**
Marshal Exp 8 (frozendict), Exp 9 (preallocate refs): both flat on the bench; value only visible on shapes not measured. For json, this means: don't add a `frozendict` fast path in the decoder, don't add an `indent`-heavy pretty-printer optimization, without a bench that actually produces those. Build the bench first (numpy-like homogeneous arrays; long ASCII key dicts; log-shaped single-line objects; large pretty-printed configs) *then* measure.

**A6 — Contamination is real.**
Marshal + pickle both had rounds poisoned by a kernel compile on the same core. Pin with `taskset -c 0`, best-of-median across 3 pinned runs, always rerun a suspicious reading on a confirmed-quiet machine. Same rule here.

## Recommended first three diffs

1. **T3** (module-level key-memo LRU in `Lib/json/decoder.py` + pass-through in `_json.c::_parse_object_unicode`): 30 LoC, maybe 60 with C side; directly ships the wins already flagged in `cpython-perf-ideas.md #14`; zero compat risk. Expected −5 to −15% on JSON-log ingestion.
2. **T1** (raw `PyObject **` array for `_parse_array_unicode`): ~80 LoC of C; pattern-identical to marshal Exp 1 which cleared the marshal campaign's biggest bar. Expected −10 to −20% on array-heavy decode.
3. **T5** (fused memchr-style escape scan in `ascii_escape_size`/`escape_size`): moderate C work but the pattern is obvious (single-pass vs two-pass) and `cpython-perf-ideas.md` already acknowledged it. Expected −15 to −30% on short-string-heavy encode.

Those three ship as independent PRs and together should clear −15 to −25% end-to-end on a realistic JSON-log workload, mirroring the cumulative deltas from the marshal and logging campaigns.
