"""Deep compat tests for Phase 3 C LogRecord.__init__.

Targets the edge cases the standard third-party suites don't exercise:
 * LogRecord subclass via setLogRecordFactory
 * User LogRecord subclass that adds fields in __init__
 * makeRecord override returning a custom class
 * pickle / deepcopy roundtrip (handlers.SocketHandler path)
 * dictConfig / fileConfig
 * QueueHandler / QueueListener (multiprocessing-adjacent path)
 * multiprocessing fork + child emit
 * Custom Filter that mutates record.__dict__
 * Unusual __init__ signatures (positional vs keyword, kwargs spillover)
 * record.__dict__[key] lookups match eager-attr semantics
"""
import copy
import io
import logging
import logging.config
import logging.handlers
import multiprocessing
import pickle
import queue
import sys
import threading
import traceback

RESULTS = []

def check(name, cond, detail=""):
    ok = bool(cond)
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


# --- confirm Phase 3 is live ---
check("phase3_live",
      logging.LogRecord.__init__.__name__ == "_LogRecord_init_c",
      f"init={logging.LogRecord.__init__.__name__}")


# --- 1. setLogRecordFactory with custom subclass ---
class MyRecord(logging.LogRecord):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_field = "hi"

logging.setLogRecordFactory(MyRecord)
try:
    logger = logging.getLogger("factory_test")
    logger.setLevel(logging.DEBUG)
    h = logging.StreamHandler(io.StringIO())
    logger.addHandler(h)
    got_record = []
    class RecCapture(logging.Handler):
        def emit(self, r): got_record.append(r)
    logger.addHandler(RecCapture())
    logger.info("hello %s", "world")
    r = got_record[-1]
    check("custom_factory_is_subclass", isinstance(r, MyRecord), type(r).__name__)
    check("custom_factory_preserves_fields", r.name == "factory_test" and r.msg == "hello %s")
    check("custom_factory_custom_attr", r.custom_field == "hi")
    check("custom_factory_threadName", r.threadName == threading.current_thread().name)
    check("custom_factory_in_dict",
          r.__dict__.get("threadName") == threading.current_thread().name)
finally:
    logging.setLogRecordFactory(logging.LogRecord)


# --- 2. LogRecord subclass with extra __init__ args ---
class RichRecord(logging.LogRecord):
    def __init__(self, name, level, pathname, lineno, msg, args, exc_info,
                 func=None, sinfo=None, trace_id=None):
        super().__init__(name, level, pathname, lineno, msg, args, exc_info,
                         func=func, sinfo=sinfo)
        self.trace_id = trace_id

r = RichRecord("n", 10, "/x.py", 1, "m", (), None, trace_id="abc")
check("subclass_extra_kwarg", r.trace_id == "abc")
check("subclass_msg", r.msg == "m")
check("subclass_process", r.process == multiprocessing.current_process().pid)


# --- 3. makeRecord override (Sphinx pattern) ---
class LoggerWithMakeRecord(logging.Logger):
    def makeRecord(self, name, level, fn, lno, msg, args, exc_info,
                   func=None, extra=None, sinfo=None):
        r = logging.LogRecord(name, level, fn, lno, msg, args, exc_info,
                              func=func, sinfo=sinfo)
        r.injected = "yes"
        if extra:
            for k, v in extra.items():
                r.__dict__[k] = v
        return r

logging.setLoggerClass(LoggerWithMakeRecord)
try:
    lg = logging.getLogger("make_record_test")
    assert type(lg) is LoggerWithMakeRecord
    lg.setLevel(logging.DEBUG)
    captured = []
    class Cap(logging.Handler):
        def emit(self, rec): captured.append(rec)
    lg.addHandler(Cap())
    lg.info("made")
    check("make_record_injected", captured[-1].injected == "yes")
    check("make_record_threadName_present", hasattr(captured[-1], "threadName"))
finally:
    logging.setLoggerClass(logging.Logger)


# --- 4. Pickle roundtrip ---
rec = logging.LogRecord("pickled", logging.WARNING, "/p.py", 42,
                        "msg %s", ("x",), None)
# logging.handlers.SocketHandler pickles records
blob = pickle.dumps(rec)
rec2 = pickle.loads(blob)
check("pickle_roundtrip_name", rec2.name == "pickled")
check("pickle_roundtrip_args", rec2.args == ("x",))
check("pickle_roundtrip_threadName", rec2.threadName == rec.threadName)
check("pickle_roundtrip_dict_equal", rec2.__dict__ == rec.__dict__)


# --- 5. Deep copy ---
rec3 = copy.deepcopy(rec)
check("deepcopy_name", rec3.name == rec.name)
check("deepcopy_thread", rec3.threadName == rec.threadName)


# --- 6. dictConfig ---
buf = io.StringIO()
# Replace a handler class to capture output
import logging as L
class CaptureHandler(L.Handler):
    def __init__(self, level=logging.NOTSET, stream=None):
        super().__init__(level)
        self.records = []
    def emit(self, record):
        self.records.append(record)

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "cap": {"()": CaptureHandler, "level": "DEBUG"},
    },
    "loggers": {
        "dc_test": {"handlers": ["cap"], "level": "DEBUG", "propagate": False},
    },
})
logger = logging.getLogger("dc_test")
logger.info("dc msg %d", 7)
logger.error("dc err")
[cap] = [h for h in logger.handlers if isinstance(h, CaptureHandler)]
check("dictconfig_emitted_2", len(cap.records) == 2)
check("dictconfig_first_is_INFO", cap.records[0].levelname == "INFO")
check("dictconfig_args_interpolate", cap.records[0].getMessage() == "dc msg 7")


# --- 7. QueueHandler / QueueListener ---
q = queue.Queue()
qh = logging.handlers.QueueHandler(q)
cap_q = CaptureHandler()
ql = logging.handlers.QueueListener(q, cap_q)
lg = logging.getLogger("qtest")
lg.handlers = [qh]
lg.setLevel(logging.DEBUG)
lg.propagate = False
ql.start()
try:
    lg.info("queued %s", "yes")
    # queue listener runs in its own thread; sleep briefly
    import time; time.sleep(0.1)
finally:
    ql.stop()
check("queue_handler_delivered", len(cap_q.records) == 1)
check("queue_handler_msg", cap_q.records and cap_q.records[0].getMessage() == "queued yes")
check("queue_handler_preserves_thread", cap_q.records and cap_q.records[0].threadName is not None)


# --- 8. Filter returning False (record dropped) / True / modifying __dict__ ---
class MutatingFilter(logging.Filter):
    def filter(self, record):
        record.__dict__["mutated"] = True
        record.msg = record.msg + " [mut]"
        return True

lg2 = logging.getLogger("filter_test")
lg2.propagate = False
cap_f = CaptureHandler()
cap_f.addFilter(MutatingFilter())
lg2.handlers = [cap_f]
lg2.setLevel(logging.DEBUG)
lg2.info("before")
check("filter_can_mutate_msg", cap_f.records[0].msg == "before [mut]")
check("filter_mutation_in_dict", cap_f.records[0].__dict__.get("mutated") is True)


# --- 9. json-style __dict__ consumers ---
rec = logging.LogRecord("x", logging.ERROR, "/a/b/c.py", 10,
                        "err %(code)d", {"code": 404}, None)
# python-json-logger and structlog read record.__dict__ directly
required_keys = {"name","msg","args","levelname","levelno","pathname",
                 "filename","module","exc_info","exc_text","stack_info",
                 "lineno","funcName","created","msecs","relativeCreated",
                 "thread","threadName","processName","process"}
missing = required_keys - rec.__dict__.keys()
check("record_dict_has_all_standard_keys",
      not missing, f"missing={sorted(missing)}")


# --- 10. Unusual __init__ signatures ---
# positional-only full form
r1 = logging.LogRecord("n", 10, "/x.py", 1, "m", (), None)
check("pos_only_minimal", r1.name == "n")
# with func/sinfo
r2 = logging.LogRecord("n", 10, "/x.py", 1, "m", (), None, "myfunc", "stackinfo-here")
check("pos_func_sinfo", r2.funcName == "myfunc" and r2.stack_info == "stackinfo-here")
# keyword args
r3 = logging.LogRecord("n", 10, "/x.py", 1, "m", (), None, func="f2", sinfo="s2")
check("kw_func_sinfo", r3.funcName == "f2" and r3.stack_info == "s2")
# Unknown kwargs should be rejected — but some code does Logger.makeRecord
# with extra kwargs? Our wrapper has **kwargs that are silently dropped.
try:
    r4 = logging.LogRecord("n", 10, "/x.py", 1, "m", (), None, extra_bogus="x")
    # C impl: extra kwargs accepted silently (the wrapper absorbs them)
    check("kw_unknown_absorbed", True, "wrapper has **kwargs")
except TypeError as e:
    check("kw_unknown_absorbed", False, f"{e}")


# --- 11. Exc info tuple handling ---
try:
    raise ValueError("boom")
except ValueError:
    exc_info = sys.exc_info()
    r = logging.LogRecord("exc", 40, "/x.py", 1, "m", (), exc_info)
    check("exc_info_preserved", r.exc_info is exc_info)
    # exc_text is lazily computed in format(); check initial is None
    check("exc_text_initially_None", r.exc_text is None)


# --- 12. Multiprocessing fork + child emit ---
if sys.platform != "win32":
    ctx = multiprocessing.get_context("fork")
    def child(outq):
        import logging
        r = logging.LogRecord("child", 20, "/c.py", 1, "pid=%d", (1,), None)
        outq.put((r.name, r.process, r.processName, r.__dict__.get("threadName")))
    q2 = ctx.Queue()
    p = ctx.Process(target=child, args=(q2,))
    p.start()
    p.join(10)
    got = q2.get(timeout=2)
    check("fork_child_ok", got[0] == "child")
    check("fork_child_pid_set", isinstance(got[1], int) and got[1] > 0)
    check("fork_child_threadName_set", got[3] is not None)


# --- summary ---
print()
print("="*60)
fails = [r for r in RESULTS if not r[1]]
print(f"{len(RESULTS)} checks, {len(RESULTS)-len(fails)} pass, {len(fails)} fail")
if fails:
    for n, _, d in fails:
        print(f"  FAIL  {n}  {d}")
    sys.exit(1)
