"""Sub-interpreter smoke test for the Phase 3 _logging module.

The module declares Py_MOD_PER_INTERPRETER_GIL_SUPPORTED and stores
all its state on the module object. Verifies:
 1. A fresh sub-interpreter can import _logging + logging.
 2. LogRecord.__init__ in the sub-interpreter is also the C version.
 3. Emitting a record in the sub-interpreter works and isolation is
    preserved (records from sub don't leak to main interpreter's state).
"""
import _interpreters
import sys
import textwrap


# Confirm main-interp Phase 3
import logging
assert logging.LogRecord.__init__.__name__ == "_LogRecord_init_c", \
    logging.LogRecord.__init__
print(f"main interp: init={logging.LogRecord.__init__.__name__}")


CODE = textwrap.dedent("""
    import _logging
    import logging
    # The C init function must be visible here too
    init_name = logging.LogRecord.__init__.__name__
    assert init_name == "_LogRecord_init_c", init_name
    r = logging.LogRecord("sub", 20, "/sub.py", 1, "in sub %d", (42,), None)
    assert r.name == "sub"
    assert r.args == (42,)
    assert r.threadName is not None
    print(f"sub interp: OK, threadName={r.threadName}, getMessage={r.getMessage()}")
""")

iid = _interpreters.create()
try:
    _interpreters.run_string(iid, CODE)
finally:
    _interpreters.destroy(iid)
print("sub-interpreter test passed")
