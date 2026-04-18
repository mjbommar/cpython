"""Free-threading stress test for Phase 3.

N threads each create M LogRecord objects concurrently and emit them
through a shared Logger + shared Handler. Verifies:
 1. No crash, no data race visible from Python.
 2. All records are received at the handler (no lost emits).
 3. threadName on each record matches the thread that created it.
"""
import logging
import sys
import threading
import time

assert logging.LogRecord.__init__.__name__ == "_LogRecord_init_c", logging.LogRecord.__init__

N_THREADS = 16
N_PER_THREAD = 5000

class Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
        self._mylock = threading.Lock()
    def emit(self, record):
        with self._mylock:
            self.records.append((record.threadName, record.msg, record.args))

logger = logging.getLogger("ft.stress")
logger.setLevel(logging.DEBUG)
col = Collector()
logger.addHandler(col)
logger.propagate = False

def worker(idx):
    tname = threading.current_thread().name
    for i in range(N_PER_THREAD):
        logger.info("t=%s i=%d", tname, i)

threads = [threading.Thread(target=worker, args=(i,), name=f"W{i}")
           for i in range(N_THREADS)]
t0 = time.time()
for t in threads: t.start()
for t in threads: t.join()
dt = time.time() - t0

total_expected = N_THREADS * N_PER_THREAD
total_got = len(col.records)
print(f"threads={N_THREADS} per-thread={N_PER_THREAD} expected={total_expected} got={total_got} elapsed={dt:.2f}s")
assert total_got == total_expected, f"lost {total_expected - total_got} records"

# threadName matches args[0] for every record
bad = [r for r in col.records if r[0] != r[2][0]]
assert not bad, f"threadName/arg mismatch on {len(bad)} records, first={bad[0]}"

# per-thread count is exact
counts = {}
for tname, _, _ in col.records:
    counts[tname] = counts.get(tname, 0) + 1
assert all(c == N_PER_THREAD for c in counts.values()), counts
print(f"per-thread counts all = {N_PER_THREAD}: OK")
print(f"total: {total_got} records, {total_got/dt:,.0f} records/sec")
