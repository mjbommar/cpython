# `uuid.uuid4()` C fast path — commands and recorded results

Branch under test:

- `/tmp/cpython-uuid-cfast`

Baseline interpreter:

- `/tmp/cpython-main-bench/python`

Candidate interpreter:

- `/tmp/cpython-uuid-cfast/python`

## Validation

Command:

```bash
./python -m test -j4 test_uuid
```

Recorded result:

```text
Using random seed: 2580252599
0:00:00 load avg: 1.14 Run 1 test in parallel using 1 worker process
0:00:00 load avg: 1.14 [1/1] test_uuid passed

== Tests result: SUCCESS ==

1 test OK.

Total duration: 229 ms
Total tests: run=116 skipped=22
Total test files: run=1/1
Result: SUCCESS
```

## Benchmarks

Baseline `uuid.uuid4()`:

```bash
/tmp/cpython-main-bench/python -m timeit -s 'import uuid' 'uuid.uuid4()'
```

```text
500000 loops, best of 5: 543 nsec per loop
```

Baseline `uuid.uuid7()`:

```bash
/tmp/cpython-main-bench/python -m timeit -s 'import uuid' 'uuid.uuid7()'
```

```text
500000 loops, best of 5: 925 nsec per loop
```

Candidate `uuid.uuid4()`:

```bash
/tmp/cpython-uuid-cfast/python -m timeit -s 'import uuid' 'uuid.uuid4()'
```

```text
1000000 loops, best of 5: 351 nsec per loop
```

Candidate `uuid.uuid7()`:

```bash
/tmp/cpython-uuid-cfast/python -m timeit -s 'import uuid' 'uuid.uuid7()'
```

```text
500000 loops, best of 5: 915 nsec per loop
```

## Interpretation

- `uuid.uuid4()` improved from `543 ns` to `351 ns` (`-35.4%`)
- `uuid.uuid7()` stayed essentially flat
- the final portable helper remained clearly faster than the rebuilt
  `main` baseline while preserving the platform-specific secure-RNG
  design
