"""Higher-scale FT stress + data-integrity check."""
import logging, threading, time, sys, os

assert logging.LogRecord.__init__.__name__ == "_LogRecord_init_c", logging.LogRecord.__init__

# Scan: record-creation directly (no handler) then full emit path.
class Collector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
        self._mylock = threading.Lock()
    def emit(self, r):
        with self._mylock:
            # Read every timing/thread/proc attr; a torn write would show.
            self.records.append((r.threadName, r.thread, r.process,
                                 r.processName, r.name, r.msg, r.args,
                                 r.created, r.levelno))

lg = logging.getLogger("scale")
lg.setLevel(logging.DEBUG)
lg.addHandler(Collector()); col = lg.handlers[-1]
lg.propagate = False

def worker():
    tname = threading.current_thread().name
    for i in range(N_PER):
        lg.info("t=%s i=%d", tname, i)

total_emitted = 0
total_elapsed = 0.0
for (T, N_PER) in [(4, 25_000), (8, 25_000), (16, 25_000), (32, 10_000)]:
    col.records.clear()
    threads = [threading.Thread(target=worker, name=f"S{i}") for i in range(T)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join()
    dt = time.time() - t0
    exp = T * N_PER
    got = len(col.records)
    # Data integrity: every record's threadName matches its first arg;
    # pid is the main process; levelno is INFO.
    bad_tn = sum(1 for r in col.records if r[0] != r[6][0])
    bad_pid = sum(1 for r in col.records if r[2] != os.getpid())
    bad_lv = sum(1 for r in col.records if r[8] != logging.INFO)
    print(f"T={T:2d} N={N_PER} expected={exp} got={got} "
          f"dt={dt:.2f}s rate={got/dt:,.0f}/s "
          f"bad_tn={bad_tn} bad_pid={bad_pid} bad_lv={bad_lv}")
    assert got == exp, (exp, got)
    assert bad_tn == 0, bad_tn
    assert bad_pid == 0, bad_pid
    assert bad_lv == 0, bad_lv
    total_emitted += got
    total_elapsed += dt

print(f"\nGRAND TOTAL: {total_emitted:,} records, "
      f"avg rate {total_emitted/total_elapsed:,.0f}/s, 0 integrity failures")
