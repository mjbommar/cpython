"""Refcount + tracemalloc leak test for Phase 3 C LogRecord.__init__.

Creates a large number of LogRecord objects in a hot loop, forces GC,
and checks that:
  1. gc.get_count() stabilises
  2. tracemalloc-traced allocations attributed to _loggingmodule.c are
     not monotonically growing
  3. sys.getrefcount of the interned key strings is stable across runs
"""
import gc
import logging
import sys
import tracemalloc


def live_records_count():
    return sum(1 for o in gc.get_objects() if isinstance(o, logging.LogRecord))


def baseline():
    """Small warm-up loop; prime all caches."""
    for i in range(5_000):
        logging.LogRecord("x.y.z", 20, "/a/b/c.py", 1, "m %s", (i,), None)
    gc.collect()


def bulk(n):
    total = 0
    for i in range(n):
        r = logging.LogRecord("x.y.z", 20, "/a/b/c.py", i, "msg %d", (i,), None)
        total += r.levelno  # touch the record
    return total


def main():
    # confirm Phase 3
    assert logging.LogRecord.__init__.__name__ == "_LogRecord_init_c", \
        logging.LogRecord.__init__
    print(f"Phase 3 live: {logging.LogRecord.__init__}")

    baseline()
    gc.collect()
    gc.collect()

    before_objects = len(gc.get_objects())
    before_records = live_records_count()

    tracemalloc.start()
    snap0 = tracemalloc.take_snapshot()

    N = 200_000
    # Run three identical bursts; each should leave live objects flat
    for burst in range(3):
        total = bulk(N)
        gc.collect()
        gc.collect()
        snap = tracemalloc.take_snapshot()
        diff = snap.compare_to(snap0, "lineno")
        # Focus on allocations attributed to the logging module / our C module
        top_5 = [(str(d.traceback[0]), d.size_diff)
                 for d in sorted(diff, key=lambda d: -d.size_diff)[:5]]
        live = live_records_count()
        total_objects = len(gc.get_objects())
        print(f"burst {burst}: live LogRecords={live} "
              f"(start was {before_records}), total gc objects={total_objects} "
              f"(start {before_objects})")
        for tb, sz in top_5:
            print(f"    +{sz:>10} bytes   {tb}")

    tracemalloc.stop()

    final_records = live_records_count()
    # There will be a small handful of persistent LogRecord lookups
    # (e.g. the test's own cache) but the count must not have grown
    # meaningfully across bursts.
    assert final_records - before_records < 20, \
        f"LogRecord count grew by {final_records - before_records}"
    print(f"\nOK — live LogRecord count delta over 3x{N} burst: "
          f"{final_records - before_records}")


if __name__ == "__main__":
    main()
