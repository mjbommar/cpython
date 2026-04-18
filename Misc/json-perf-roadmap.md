# CPython `json` perf roadmap

Research consolidation for a `json` module optimization campaign. Branch
`exp-json/research` (off `main` at `2faceeec5c0`).  Built from five
parallel Opus sub-agent analyses:

| agent | lens |
|-------|------|
| **P** | pattern-transfer from marshal / pickle / logging campaigns |
| **C** | `Modules/_json.c` code archaeology |
| **T** | compiler-theory perspective (peephole, partial eval, SIMD) |
| **D** | data-scientist realistic workloads + profiling |
| **S** | security / correctness guardrails |

Consensus items (flagged independently by ≥3 agents) are marked **★**.

---

## 1. Winning patterns from prior campaigns

Compact catalogue. For the full diary, see `Misc/marshal-perf-diary.md`,
`Misc/pickle-perf-diary.md`, `Misc/logging-perf-diary.md`.

| id | pattern | example win |
|----|---------|-------------|
| P1 | replace `PyList`-backed accumulator with raw `PyObject**` growable array | marshal Exp 1: −22.6% on small-tuple loads |
| P2 | tagged-pointer / collapse parallel state arrays | marshal Exp 2: −5.9% on top of P1 |
| P3 | match atomics-first dispatch order from the C reference | pickle F1: up to −30.4% on atomic-heavy workloads |
| P4 | exact-type fast path that skips the generic iterator/batching layer | pickle Exp 4: −17 to −22% on nested containers |
| P5 | precomputed small-value byte/string cache | pickle F4: −9.9% on int-heavy encode |
| P6 | inline a method call whose common-case body is trivial | pickle Exp D: −5 to −10% consistently |
| P7 | inline one-byte opcode emission into the caller | pickle F2: −1 to −2% consistently |
| P8 | force `static inline` on tiny helpers | marshal Exp 7: −3% free |
| P9 | pure-function result cache keyed on immutable input | logging L1: −10% end-to-end from `_pathname_to_fields_cache` + `_internal_frame_cache` |
| P10 | snapshot immutable module state at install; stop re-looking it up | logging L3: level-name cache, main-thread ident cached once |
| P11 | preallocate typed fast-path struct at `__init__` instead of per-call | logging existing `isEnabledFor._cache` |

**Anti-patterns (things that cost us time / regressed):**

| anti | don't do this | why |
|------|---------------|-----|
| A1 | introduce a Python-level counter to replace a C-method call | pickle F3: `current_frame_size` regressed 3-5% everywhere |
| A2 | re-specialise a codec that Python already specialises | pickle F5: `isascii()` + `.encode('ascii')` was flat — utf-8 codec memcpys ASCII already |
| A3 | hand-rolled `__dict__` probe vs `PyType_Lookup`'s type-attribute cache | pickle Exp B: 17-36% regression |
| A4 | cross the Python↔C boundary just to shave C-level work | logging Phase 2: −38% isolated ate by boundary, net +1.0% |
| A5 | specialise for shapes the bench doesn't exercise | marshal Exp 8/9: flat on bench, invisible value |

---

## 2. Guardrails (hard constraints on every change)

Compressed from agent S. The full checklist (with per-item "why" and
regression tests) is in `Misc/json-perf-data/guardrails.md` (agent
output copied verbatim). The golden rule:

> **Exact-type fast paths require `Py_TYPE(obj) == &PyFoo_Type` (or
> `PyFoo_CheckExact`), never `PyFoo_Check`.** The latter admits
> subclasses whose `__repr__` / `__iter__` / `__lt__` / `items()` may
> be overridden.  Counter-examples that MUST remain correct:
> `bool` vs `int`, `IntEnum` vs `int`, `str` subclass with custom
> `__str__` (gh-148241), `OrderedDict`, `Counter`, `defaultdict`,
> `list` subclass with custom `__iter__`.

Fixed self-check battery (any patch that fails these is rejected before
benchmarking):

```python
import json, enum, decimal, collections
class IE(enum.IntEnum): X = 1
class SS(str): pass
class LS(list):
    def __iter__(self): return iter(reversed(list.__iter__(self).__self__))
class DS(dict):
    def items(self): return [('z', 1), ('a', 2)]
assert json.dumps(True) == 'true'                   # bool-before-int
assert json.dumps(IE.X) == '1'                      # IntEnum -> int value
assert json.dumps(SS("x")) == '"x"'                 # str subclass
assert json.dumps(LS([1,2,3])) == '[3, 2, 1]'       # list-subclass __iter__
assert json.dumps(DS()) == '{"z": 1, "a": 2}'       # dict-subclass items()
assert json.dumps(-0.0) == '-0.0'                   # signed zero
assert json.loads("1"*500) == int("1"*500)          # big int unbounded
a=[]; a.append(a)
try: json.dumps(a); assert False, "should raise"
except ValueError: pass                             # check_circular
assert json.loads('{"z":1,"a":2}', object_pairs_hook=list) == [('z',1),('a',2)]
assert json.loads('"\\ud83d"') == '\ud83d'         # lone surrogate preserved
assert json.dumps('\ud83d', ensure_ascii=False) == '"\ud83d"'
```

Additional constraints to audit per-change:
- No new mutable module-level state (module is
  `Py_MOD_PER_INTERPRETER_GIL_SUPPORTED` + `Py_MOD_GIL_NOT_USED`).
- `_Py_EnterRecursiveCall` at every nesting level; no hand-rolled stack
  that silently drops the depth bound.
- User hooks (`default`, `object_hook`, `parse_float`, etc.) may raise
  *any* exception; propagation must not be reordered by a fast path.
- `check_circular=True` markers: insert before recursing, delete on
  success. Don't skip on "known acyclic" without an explicit opt-in.
- Float repr must round-trip (Python dtoa); no `%.17g` / `%.15f`
  substitutes.
- Lone surrogates preserved on both encode and decode.

---

## 3. Realistic benchmark scenarios

From agent D. Consolidate into one file
`Misc/json-perf-data/json_realistic_bench.py` modelled on
`logging_realistic_bench.py`. The minimum set before measuring any
experiment:

| id | scenario | shape | call |
|----|----------|-------|------|
| **J1** | Web API response dumps | 10-14 key dict w/ short ascii strings, mixed types, 5 nested items | `dumps`, 50 000× |
| **J2** | NDJSON log shipping dumps | structlog-shape dict (10 keys), 400 B/line | `dumps`, 200 000× |
| **J3** | NDJSON ingest loads | same shape as J2, same key names (high key-memo hit rate) | `loads`, 200 000× |
| **J4** | Bulk dump | list of 100 000 uniform dicts, one `dumps` call | single `dumps` |
| **J5** | Unicode-heavy ensure_ascii=True | CJK + emoji dict values, 5 000 records | `dumps`, 10× |
| **J6** | Unicode-heavy ensure_ascii=False | same payload, ascii=False | `dumps`, 10× |
| **J7** | Numeric-heavy | list of 20 000 `{t,x,y,n,big}` records, floats + a 64-digit bigint | `dumps`, 10× |
| **J8** | Config file loads (cold) | 30 KB pyproject/OpenAPI shape, 200 keys, depth 4-6 | `loads`, 2 000× |

Methodology (same hygiene as marshal/pickle/logging):
- `taskset -c 0`, fresh subprocess per scenario (to defeat inter-run
  string interning contamination), 7-run trimmed mean hi/lo-trimmed.
- Warm-up pass discarded. GC disabled for J4/J7 only.
- Report per-call µs AND MB/s (serialized bytes/s) — SRE-relevant.
- Report `ensure_ascii=True` and `False` separately; never blended.
- Real-data corpus pointers: GitHub Archive gzipped JSONL, HuggingFace
  datasets (`allenai/c4`, `fineweb`), PyPI `<pkg>/json` responses,
  Kubernetes `swagger.json`. See agent D output for URLs.

---

## 4. Ranked experiment list

Each experiment has: location, current shape, proposed change, expected
win, risk, applicable patterns.  Ordering is expected-win × evidence-strength.

### E1. ★ Single-pass SWAR/memchr ASCII-escape scan (**highest win**)

- **Location**: `Modules/_json.c:161-307` (`ascii_escape_size`,
  `ascii_escape_unicode_and_size`, `write_escaped_ascii`).
- **Current**: two full passes over every string — one to compute
  output size (checks each char against `S_CHAR(c)`), one to emit.
- **Proposed**: for `kind == PyUnicode_1BYTE_KIND` (the overwhelmingly
  common case — ASCII dict keys + short values), scan with a 256-entry
  classifier bitmap or SWAR word-at-a-time for the first
  escape-needing byte. If none found, take the no-escape branch
  directly (current code already has one at `:256`); avoid the second
  pass entirely. For 2/4-byte kinds, fold size computation into the
  emit loop with a generous initial writer estimate.
- **Expected win**: **10-30%** on string-heavy `dumps` (J1, J2, J5-ascii).
- **Patterns**: P4 (exact-type: `kind == 1BYTE`), compiler-theory lens 5.
- **Risk**: control-char mask must cover `\0..\x1f`, `"`, `\`, and for
  `ensure_ascii=True` everything `>= 0x7f`. Lone surrogates (for the
  2-byte path) must be preserved.
- **Self-check**: all scenarios in §2's battery plus
  `dumps("a\x00b\x01\x1fc")`, a CJK+emoji string with/without
  `ensure_ascii`.

### E2. ★ Kind-specialised decoder string scan

- **Location**: `Modules/_json.c:498-515` (`scanstring_unicode` inner
  loop).
- **Current**: `PyUnicode_READ(kind, buf, next)` per character — macro
  dispatches on `kind` every iteration, compiler can't hoist across
  recursion.
- **Proposed**: hoist the `kind` dispatch to function entry; specialise
  into three flat scanners (`ucs1`, `ucs2`, `ucs4`). For `ucs1`, use a
  byte-table `if (table[*p]) break;` that auto-vectorises under `-O2`.
- **Expected win**: **3-8%** on string-heavy `loads` (J3, J8).
- **Patterns**: P4 (exact kind), T5 (strength reduction).
- **Risk**: `strict=0` legacy path (accepts raw control chars) must
  remain correct — two tables.

### E3. Exact-type dispatch reorder in `encoder_listencode_obj`

- **Location**: `Modules/_json.c:1568-1667`.
- **Current**: `Py_None`/`Py_True`/`Py_False` identity, then
  `PyUnicode_Check`, `PyLong_Check`, `PyFloat_Check`, `PyList_Check ||
  PyTuple_Check`, `PyAnyDict_Check`. Each `PyFoo_Check` walks `tp_flags`
  / MRO. `str` is usually the most common list/dict item.
- **Proposed**: lift `PyTypeObject *tp = Py_TYPE(obj);` once; test
  identity against `&PyUnicode_Type`, `&PyDict_Type`, `&PyList_Type`,
  `&PyLong_Type`, `&PyFloat_Type`, `&PyTuple_Type` in frequency order
  (string, dict, long, list, float, tuple). Fall through to the
  existing subclass-aware chain only on miss.
- **Expected win**: **2-5%** everywhere, most on J1/J2.
- **Patterns**: P3, P4.
- **Risk**: none — exact-type branches are a pure subset; subclass
  chain is preserved.

### E4. Module-level decoder key-memo cache (with LRU bound)

- **Location**: `Lib/json/decoder.py:349` (`self.memo = {}` per
  decoder); `Modules/_json.c:789-792`
  (`PyDict_SetDefaultRef(s->memo, key, key, ...)`).
- **Current**: every `JSONDecoder` gets a fresh memo. Repeated
  `json.loads(line)` on NDJSON misses the shared-key opportunity.
- **Proposed**: module-level size-bounded intern cache (4096 entries,
  evict-on-insert-past-N). Keep per-instance memo as fallback when any
  hook is active (`object_hook`, `parse_int`, etc. all imply the user
  may inspect key identity, so don't risk interning). Already flagged
  in `Misc/cpython-perf-ideas.md #14`.
- **Expected win**: **5-15%** on J3, J5 (NDJSON log ingest).
- **Patterns**: P9, P10.
- **Risk**: bounded memory growth (≤200 KB for 4096 keys); no change
  when any hook is passed.

### E5. Raw `PyObject**` accumulator for `_parse_array_unicode`

- **Location**: `Modules/_json.c:910` (array decode).
- **Current**: `PyList_Append` per element — amortized geometric
  growth + function-call overhead.
- **Proposed**: local `PyObject **vals; Py_ssize_t len, cap;` growable
  array; `PyList_New(len)` + `PyList_SET_ITEM` bulk memcpy at the end
  (or `_PyList_AppendTakeRef` if available).  Marshal Exp 1 pattern.
- **Expected win**: **10-20%** on array-heavy decode (J4, J8).
- **Patterns**: P1.
- **Risk**: none — same observable behaviour, fewer function calls.

### E6. Partial-eval the Encoder config at construction

- **Location**: `Modules/_json.c:1346-1356` (`encoder_new` already does
  this for `fast_encode` — generalise it).
- **Current**: `s->indent`, `s->markers`, `s->sort_keys`, `s->skipkeys`,
  `s->allow_nan` re-tested on every recursive descent.
- **Proposed**: at `encoder_new`, pick one of (up to) 32 pre-compiled
  specialisations — in practice 2-3 (default; `indent=...`;
  `sort_keys=True`). Analogous to bytecode `LOAD_ATTR_INSTANCE_VALUE`:
  cache the "type-version" of the encoder config.
- **Expected win**: **5-8%** on J1/J2/J3 default-config dumps.
- **Patterns**: P10 (snapshot state), P11 (fast-path struct).
- **Risk**: moderate — more specialisation surface to test. Must
  preserve all existing subclass hooks.
- **Effort**: higher than E1-E5. Defer until after the big wins land.

### E7. Direct `PyOS_double_to_string` → writer for floats

- **Location**: `Modules/_json.c:1510-1534`, `1599-1604`
  (`encoder_encode_float` + `_steal_accumulate`).
- **Current**: `PyFloat_Type.tp_repr(obj)` allocates a temp PyUnicode;
  `_steal_accumulate` copies into writer; DECREF.
- **Proposed**: `PyOS_double_to_string(d, 'r', 0, Py_DTSF_ADD_DOT_0,
  NULL)` → `PyUnicodeWriter_WriteASCII(writer, buf, len)` → `PyMem_Free`.
  No temp PyUnicode allocation.
- **Expected win**: **3-6%** on J7 (float-heavy).
- **Patterns**: P6 (inline), P7 (skip one-shot allocation).
- **Risk**: must preserve shortest round-trip. Existing
  `test_json.test_floats` locks it down.

### E8. Stack-allocated circular-marker set (replace `PyLong_FromVoidPtr` + dict)

- **Location**: `Modules/_json.c:1620-1636, 1813, 1933`.
- **Current**: `PyLong_FromVoidPtr(obj)` + three dict ops per container
  entry, even for acyclic payloads (the 99% case).
- **Proposed**: C-level open-addressing `uintptr_t` hashset with stack
  storage for ≤16 entries, heap spill after. Happy path: one hash +
  one insert + one remove, no Python allocation. Fall back to the
  current `markers` dict when `check_circular=False` path didn't set
  one up.
- **Expected win**: **2-4%** on container-heavy encode (J1, J4).
- **Patterns**: P2 (collapse parallel state), compiler-theory escape analysis.
- **Risk**: must keep `check_circular=False` path (no markers) and the
  exact error text of `ValueError("Circular reference detected")`.

### E9. Small-int fast path in `_match_number_unicode`

- **Location**: `Modules/_json.c:984-1096`.
- **Current**: copy chars into a `PyBytes`, call `PyLong_FromString`.
- **Proposed**: for `kind == 1BYTE && n <= 18 && !is_float`, parse
  into a `Py_ssize_t` inline; `PyLong_FromSsize_t`. CPython's small-int
  cache already dedups [-5, 256].
- **Expected win**: **10-25%** on integer-heavy decode (J3, J4).
- **Patterns**: P4 (exact-kind fast path), P5 (small-int cache).
- **Risk**: must fall back cleanly when number overflows int64 or is a
  float. Stack buffer `char buf[32]` for safety.

### E10. Fuse dict separator writes (non-indent path)

- **Location**: `Modules/_json.c:1715-1731` (`encoder_encode_key_value`).
- **Current**: non-indented dict writes 4 strings per pair:
  `item_separator`, `"key"`, `key_separator`, value. All via
  `PyUnicodeWriter_WriteStr`.
- **Proposed**: at `encoder_new`, precompute `item_sep_plus_quote` and
  `close_quote_plus_key_sep` as ASCII C strings. Replace 3 of the 4
  `WriteStr` calls with `WriteASCII` (no `PyUnicode_Check`, no
  refcount).
- **Expected win**: **3-5%** on J1/J2 default-config dumps.
- **Patterns**: P5 (precomputed bytes), P7 (inline one-byte emission).
- **Risk**: none while separators are ASCII (the default). Fall back
  to current `WriteStr` when user passes non-ASCII separators.

### E11 and lower (deferred / bundle-only)

| id | summary | est | notes |
|----|---------|----:|-------|
| E11 | `PyUnicodeWriter` initial size hint at encode entry | 1-2% | bundle with E3 |
| E12 | `PyDict_Next` with `_PyDict_NewPresized(8)` in object decode | 1-2% | small, boring |
| E13 | Sort-keys path without 2-tuple boxing | 2-6% | only when `sort_keys=True` |
| E14 | Pure-Python encoder subclass path: hoist closures into module-level | 15-25% | only for users with `cls=MyEncoder` overriding `default` |

### Out of scope / don't bother (already optimised)

Per agent C: empty-container fast paths, indent-cache memoisation
(already textbook peephole), `fast_encode` function-pointer
residualisation (already in place), `PyDict_SetDefaultRef` key memo,
`_build_rval_index_tuple`. Trying to out-optimise these just adds
code.

---

## 5. Sequencing

Suggested experiment order, mirroring the marshal/pickle campaign
cadence:

1. **Build the bench first.** `Misc/json-perf-data/json_realistic_bench.py`
   covering J1-J8 + the `guardrails.md` self-check battery gated as a
   pre-benchmark sanity step.
2. **E3** (dispatch reorder) — smallest safest change, pure C, locks
   in ~2-5% and establishes the bench loop.
3. **E1** (SWAR escape scan) — highest-leverage single change; biggest
   decision the rest of the campaign hangs on.
4. **E5** (array raw accumulator) — marshal-Exp-1 pattern, very safe.
5. **E4** (key-memo cache) — pure Python side; lowest risk, easy to
   revert; ships independently.
6. **E2** (decoder string scan) — encoder mirror; similar shape to E1.
7. **E9** (small-int fast path) — hits numeric workloads.
8. **E10** (fuse separator writes).
9. **E7** (float → writer direct).
10. **E8** (stack-allocated marker set).
11. **E6** (partial-eval encoder) — do this last; it's the
    highest-complexity change and benefits from E1/E3 already shipping
    (so we can measure the residual win accurately).

Stop and reassess after E4 if we've already cleared −15% aggregate on
J1+J2+J3 — at that point the marginal returns may not justify the
residual C complexity, exactly like logging Phase 2.

---

## 6. What we will measure / what we refuse to measure

Measure:
- Per-call µs for each of J1-J8, trimmed mean, in isolated subprocesses.
- MB/s (serialized bytes / wall time).
- `perf stat -e cycles,instructions,cache-misses,branch-misses`
  on J1 + J3 — branch-miss delta is the headline signal for E1/E2.
- Third-party regression suites at the end: `simplejson`, `orjson`
  interop where we're pretending to be stdlib, `jsonschema`,
  `pydantic` serialisation path, `pytest-benchmark`'s `test_json`, a
  `fastapi` response-model round-trip.

Do not measure:
- `json.dumps({})` or `json.loads("[]")` — those hit empty-container
  fast paths and tell us nothing.
- "improvement on the last PGO/LTO build" without a separate run on
  `--enable-optimizations=no` — PGO can hide branch misprediction wins.
- "improvement" from changes that fail the §2 self-check battery.
- Regressions attributed to E-foo when we haven't reproduced on a
  pinned-quiet machine (see marshal/pickle lesson A6).

---

## Appendix A — Raw agent outputs

The full agent responses are preserved verbatim under
`Misc/json-perf-data/research/`:

- `agent-P-pattern-transfer.md`
- `agent-C-json-archaeology.md`
- `agent-T-compiler-theory.md`
- `agent-D-workloads-profiling.md`
- `agent-S-guardrails.md`
