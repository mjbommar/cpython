"""
Profile where pure-Python logging spends time in two scenarios:
  A) Disabled log (logger.debug filtered out) — very common on production
  B) Emitted log (logger.info through a StreamHandler → bytesio)

Both with a realistic logger hierarchy + format string.
"""
import cProfile
import io
import logging
import pstats
import sys
import time


def setup_tree(root_level=logging.INFO):
    """Build a realistic nested logger hierarchy like a web app would have."""
    # Reset from any prior test
    logging.shutdown()
    logging.Logger.manager.loggerDict.clear()
    root = logging.getLogger()
    root.handlers.clear()

    buf = io.BytesIO()
    h = logging.StreamHandler(stream=io.TextIOWrapper(buf, write_through=True))
    h.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s:%(lineno)d - %(message)s'
    ))
    root.addHandler(h)
    root.setLevel(root_level)

    # Realistic hierarchy — uvicorn/fastapi-style
    loggers = [
        logging.getLogger('myapp'),
        logging.getLogger('myapp.api'),
        logging.getLogger('myapp.api.routes'),
        logging.getLogger('myapp.api.routes.users'),
        logging.getLogger('myapp.db'),
        logging.getLogger('myapp.db.conn'),
    ]
    return loggers, buf


def scenario_A_disabled(n):
    """Most production logs are DEBUG and filtered. This is THE hot path."""
    loggers, buf = setup_tree(root_level=logging.INFO)
    picked = [loggers[3], loggers[5], loggers[0]]
    for _ in range(n):
        for lg in picked:
            lg.debug("this message is not emitted: %s %d", "payload", 42)


def scenario_B_emitted(n):
    """Actually emits. Tests LogRecord.__init__ + handler dispatch + format."""
    loggers, buf = setup_tree(root_level=logging.INFO)
    picked = [loggers[3], loggers[5], loggers[0]]
    for _ in range(n):
        for lg in picked:
            lg.info("request=%s status=%d took=%.3fms", "req-42", 200, 0.123)


def time_it(fn, *args, **kwargs):
    t0 = time.perf_counter()
    fn(*args, **kwargs)
    return time.perf_counter() - t0


if __name__ == "__main__":
    print("=" * 70)
    print("Wall-time check (3 runs each, pick min):")
    for name, fn, n in [
        ("disabled (filtered) 100k",  scenario_A_disabled, 100_000),
        ("emitted (produces output) 50k", scenario_B_emitted,  50_000),
    ]:
        times = [time_it(fn, n) for _ in range(3)]
        print(f"  {name:40s}  min={min(times):.4f}s")
    print()
    print("=" * 70)
    print("cProfile for scenario B (emitted 10k), top 20 by cumtime:")
    pr = cProfile.Profile()
    pr.enable()
    scenario_B_emitted(10_000)
    pr.disable()
    st = pstats.Stats(pr).sort_stats("cumulative")
    st.print_stats(20)
    print()
    print("=" * 70)
    print("cProfile for scenario A (disabled 100k), top 20:")
    pr = cProfile.Profile()
    pr.enable()
    scenario_A_disabled(100_000)
    pr.disable()
    st = pstats.Stats(pr).sort_stats("cumulative")
    st.print_stats(20)
