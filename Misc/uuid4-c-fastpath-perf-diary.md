# `uuid.uuid4()` C fast path — experiment diary

Branch: `exp-uuid/c-fastpath`, off `main` at `cecf564073f`.

## Goal

Evaluate whether `uuid.uuid4()` can be made meaningfully faster without
regressing:

- cryptographic-strength randomness semantics
- platform-specific OS RNG expectations
- the existing pure-Python fallback in `Lib/uuid.py`
- compatibility with `_uuid` builds on platforms that lack a usable
  C-level secure RNG entry point

## Process

1. Start from the current `uuid.uuid4()` implementation in `Lib/uuid.py`
   and measure the rebuilt `main` baseline.
2. Prototype a small `_uuid` helper that returns the fully-masked UUID
   integer directly from C.
3. Review the OS-contract constraints and rework the helper so it uses
   native secure-RNG paths rather than a Linux-only shortcut.
4. Rebuild and rerun `test_uuid` plus the `uuid4()` / `uuid7()`
   microbenchmarks.
5. Summarize the branch-local recommendation and feed it back into
   `Misc/cpython-perf-ideas.md`.

## Baseline

Current `main` `uuid.uuid4()` still does:

- `os.urandom(16)`
- `int.from_bytes(...)`
- Python-level version / variant masking
- `UUID._from_int(...)`

That is already fairly lean, but it still pays for a Python round-trip
through a 128-bit integer on every call.

## Candidate designs

- **Baseline** — current pure-Python `uuid.uuid4()`
- **Initial C helper prototype** — `_uuid.generate_random_int()`
  returning the final UUID integer directly from C
- **Platform-compatible helper** — same basic helper, but reworked to
  follow each platform's native secure RNG contract and to keep `_uuid`
  on the limited C API

## OS-contract decisions

The final branch-local design keeps these constraints:

- **Windows**: use `BCryptGenRandom` with
  `BCRYPT_USE_SYSTEM_PREFERRED_RNG`
- **BSD / macOS family**: use `arc4random_buf()` when available, or
  `arc4random()` as a byte filler fallback
- **Unix with `getrandom()`**: use blocking `getrandom(..., 0)`,
  retrying on `EINTR`
- **Unix fallback chain**: if the runtime reports `ENOSYS`, fall back
  to `getentropy()` and then `/dev/urandom`
- **No nonblocking entropy shortcut**: the helper does not use a
  `GRND_NONBLOCK` / `_PyOS_URandomNonblock`-style path
- **Pure-Python fallback stays intact**: `Lib/uuid.py` only enables the
  helper when `_uuid` advertises `has_uuid_generate_random`
- **Limited C API restored**: the final helper uses the public
  `PyLong_FromUnsignedNativeBytes()` APIs available in the 3.14 limited
  C API surface instead of the private `_PyLong_FromByteArray`

## Final branch shape

Files changed on the experiment branch:

- `Modules/_uuidmodule.c`
- `Lib/uuid.py`
- `Lib/test/test_uuid.py`
- `Modules/Setup.stdlib.in` (already part of the earlier prototype
  commit; see "Open question" below)

Runtime behavior of the final helper:

- `_uuid` exports `has_uuid_generate_random`
- `Lib/uuid.py` only binds `_generate_random_int` when that flag is true
- `uuid.uuid4()` continues to fall back to the pure-Python
  `os.urandom(16)` path when the helper is absent or disabled

## Results

Benchmarks were rerun against rebuilt binaries:

- baseline: `/tmp/cpython-main-bench/python`
- candidate: `/tmp/cpython-uuid-cfast/python`

Exact commands and outputs are also stored in
`Misc/uuid4-c-fastpath-perf-data/README.md`.

### Final branch versus rebuilt `main`

- `uuid.uuid4()`:
  - baseline: `500000 loops, best of 5: 543 nsec per loop`
  - candidate: `1000000 loops, best of 5: 351 nsec per loop`
  - improvement: about `-35.4%`
- `uuid.uuid7()`:
  - baseline: `500000 loops, best of 5: 925 nsec per loop`
  - candidate: `500000 loops, best of 5: 915 nsec per loop`
  - effectively flat; this branch is a `uuid4()` experiment, not a
    meaningful `uuid7()` optimization

### Cost of the compatibility cleanup

Before the platform-contract and limited-API cleanup, the
Linux-only prototype had measured roughly:

- `uuid.uuid4()`: `329 nsec`

So the more portable final branch gives back a little speed, but still
keeps most of the win:

- `329 nsec -> 351 nsec` on the branch itself
- still much better than rebuilt `main` at `543 nsec`

## Validation

Local validation on the final branch state:

- `./configure --quiet`
- `make -j4`
- `./python -m test -j4 test_uuid`

Additional helper sanity check:

- `_uuid` imports
- `_uuid.has_uuid_generate_random == 1` on the local Linux build
- `uuid._generate_random_int is _uuid.generate_random_int`

The branch also adds a targeted fallback regression in
`test_uuid4_helper_fallback()` to keep the pure-Python `os.urandom`
path pinned when the helper is unavailable.

## Open question

The remaining non-runtime issue is module shape, not OS randomness
semantics.

The current experiment branch still carries the earlier prototype's
change to make `_uuid` available as a tiny helper module even without
external `libuuid` support. That made the experiment easy to build and
measure on Linux, but it is a build-system / policy decision separate
from the runtime fast path itself.

In other words:

- the secure-RNG fast path now has a sensible cross-platform runtime
  design
- the remaining upstream-design question is whether `_uuid` should also
  become a more general always-built helper module

That question should be validated with fork CI on Windows and macOS
before treating the branch as PR-ready.

## Recommendation

1. Keep the C fast path as a serious candidate. The final branch still
   improves `uuid.uuid4()` by about `35%` on the rebuilt binary.
2. Keep the current runtime design constraints:
   - platform-native secure RNG
   - helper gating via `has_uuid_generate_random`
   - pure-Python fallback in `Lib/uuid.py`
3. Treat the `_uuid` build-shape decision as a separate review topic.
   It should be called out explicitly in any PR split or diary update,
   because it is broader than the perf change itself.
