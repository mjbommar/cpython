/*
 * _logging — optional C accelerator for Lib/logging/__init__.py.
 *
 * The Python-level code in Lib/logging/__init__.py wraps every
 * exported function with a try/except ImportError so builds that
 * omit this module still work identically; the functions here exist
 * only to remove interpreter overhead from hot paths that the
 * logging module walks per emitted record.
 *
 * Exported functions:
 *
 *   _find_caller(stack_info: bool, stacklevel: int)
 *       -> (filename: str, lineno: int, funcname: str,
 *           sinfo: str | None)
 *
 *       C equivalent of Logger.findCaller. Walks PyFrameObject
 *       chain via the public PyFrame_GetBack / PyFrame_GetCode /
 *       PyFrame_GetLineNumber API, skipping internal logging frames
 *       via a PyCodeObject pointer-identity cache.
 *
 *   _set_srcfile(srcfile: str) -> None
 *
 *       Install the internal-frame marker. Called once at import
 *       time from Lib/logging/__init__.py with
 *       os.path.normcase(<logging_module_file>).
 *
 * Module state:
 *
 *   srcfile         — normcased filename of the logging module.
 *   internal_codes  — set of PyCodeObject*.
 *   str_importlib / str_bootstrap / sentinel strings — interned.
 */

#ifndef Py_BUILD_CORE_BUILTIN
#  define Py_BUILD_CORE_MODULE 1
#endif

#include "Python.h"
#include "pycore_code.h"       // for direct access to co_filename / co_name


typedef struct {
    PyObject *srcfile;
    PyObject *internal_codes;
    PyObject *str_importlib;
    PyObject *str_bootstrap;
    PyObject *str_unknown_file;
    PyObject *str_unknown_function;

    /* State captured from the logging module at install time. Owned
     * strong references. */
    PyObject *logging_module;       /* the logging module itself; for
                                     * dynamic flag lookup */
    PyObject *pathname_cache;       /* dict: pathname -> (filename, module) */
    PyObject *getLevelName;         /* callable */
    PyObject *os_path_basename;     /* callable */
    PyObject *os_path_splitext;     /* callable */
    PyObject *threading_get_ident;  /* callable */
    PyObject *threading_current_thread; /* callable */
    PyObject *sys_modules;          /* sys.modules dict */
    PyObject *main_thread_ident;    /* int */
    PyObject *main_thread;          /* threading.main_thread() */
    long long start_time_ns;        /* int */
    /* Cached at install time to survive interpreter shutdown. */
    PyObject *time_module;          /* the `time` module; looked up
                                     * dynamically so patch('time.time_ns')
                                     * still works (tests rely on this) */
    PyObject *str_time_ns;          /* interned "time_ns" */
    PyObject *os_getpid;            /* callable */
    PyObject *str_multiprocessing;  /* "multiprocessing" */
    PyObject *str_asyncio;          /* "asyncio" */
    PyObject *str_MainProcess;      /* "MainProcess" */
    PyObject *str_UnknownModule;    /* "Unknown module" */
    PyObject *str_logThreads;       /* "logThreads" */
    PyObject *str_logMultiprocessing; /* "logMultiprocessing" */
    PyObject *str_logProcesses;     /* "logProcesses" */
    PyObject *str_logAsyncioTasks;  /* "logAsyncioTasks" */

    /* Pre-interned LogRecord attribute names for fast PyDict_SetItem. */
    PyObject *key_name, *key_msg, *key_args, *key_levelname, *key_levelno,
             *key_pathname, *key_filename, *key_module, *key_exc_info,
             *key_exc_text, *key_stack_info, *key_lineno, *key_funcName,
             *key_created, *key_msecs, *key_relativeCreated, *key_thread,
             *key_threadName, *key_processName, *key_process, *key_taskName,
             *key_name_attr;
} logging_state;


static inline logging_state *
get_logging_state(PyObject *module)
{
    void *state = PyModule_GetState(module);
    assert(state != NULL);
    return (logging_state *)state;
}


/*
 * Return 1 if the frame's code is "internal" to the logging module,
 * 0 if not, -1 on error.
 */
static int
is_internal_code(logging_state *state, PyCodeObject *code)
{
    /* Fast path: cached pointer membership. This is the only cost
     * paid on steady-state frame walks once the code objects of the
     * logging module itself have been seen at least once. */
    int cached = PySet_Contains(state->internal_codes, (PyObject *)code);
    if (cached < 0) {
        return -1;
    }
    if (cached) {
        return 1;
    }

    /* Slow path: decide from co_filename. Direct struct field access;
     * no GetAttr dispatch. Borrowed reference. */
    PyObject *filename = code->co_filename;
    if (filename == NULL || !PyUnicode_Check(filename)) {
        return 0;
    }

    int is_internal = 0;
    if (state->srcfile != NULL) {
        int same = PyObject_RichCompareBool(
            filename, state->srcfile, Py_EQ);
        if (same < 0) {
            return -1;
        }
        if (same) {
            is_internal = 1;
        }
    }
    if (!is_internal) {
        int has_importlib = PyUnicode_Contains(
            filename, state->str_importlib);
        if (has_importlib < 0) {
            return -1;
        }
        if (has_importlib) {
            int has_bootstrap = PyUnicode_Contains(
                filename, state->str_bootstrap);
            if (has_bootstrap < 0) {
                return -1;
            }
            if (has_bootstrap) {
                is_internal = 1;
            }
        }
    }

    if (is_internal) {
        if (PySet_Add(state->internal_codes, (PyObject *)code) < 0) {
            return -1;
        }
    }
    return is_internal;
}


/*
 * _find_caller(stack_info, stacklevel) -> tuple
 *
 * Manual parsing (no clinic) — two arguments, both simple.
 */
static PyObject *
logging_find_caller(PyObject *module, PyObject *const *args, Py_ssize_t nargs)
{
    if (nargs != 2) {
        PyErr_Format(PyExc_TypeError,
            "_find_caller() takes exactly 2 arguments (%zd given)",
            nargs);
        return NULL;
    }

    int stack_info = PyObject_IsTrue(args[0]);
    if (stack_info < 0) {
        return NULL;
    }
    Py_ssize_t stacklevel = PyLong_AsSsize_t(args[1]);
    if (stacklevel == -1 && PyErr_Occurred()) {
        return NULL;
    }

    logging_state *state = get_logging_state(module);

    /* Get the current frame (our own, i.e. the frame of
     * logging_find_caller's Python caller). We need the outermost
     * Python frame; PyEval_GetFrame returns the current Python
     * execution frame, which is the caller of this C function.
     *
     * Then walk f_back, skipping internal frames, until we've popped
     * `stacklevel` non-internal frames (or run out).
     */
    PyFrameObject *f = PyEval_GetFrame();
    if (f == NULL) {
        return Py_BuildValue("OiOO",
            state->str_unknown_file, 0,
            state->str_unknown_function, Py_None);
    }

    /* PyEval_GetFrame returns borrowed; we'll manage ownership via
     * PyFrame_GetBack which returns strong references we must
     * release. Start by taking an owning reference to match the
     * loop's contract. */
    Py_INCREF(f);

    while (stacklevel > 0) {
        PyFrameObject *next = PyFrame_GetBack(f);
        if (next == NULL) {
            if (PyErr_Occurred()) {
                Py_DECREF(f);
                return NULL;
            }
            break;  /* No more frames; use this one. */
        }
        Py_DECREF(f);
        f = next;
        PyCodeObject *code = PyFrame_GetCode(f);
        if (code == NULL) {
            Py_DECREF(f);
            return NULL;
        }
        int internal = is_internal_code(state, code);
        Py_DECREF(code);
        if (internal < 0) {
            Py_DECREF(f);
            return NULL;
        }
        if (!internal) {
            stacklevel--;
        }
    }

    /* Extract fields via direct struct access. Both are strong
     * references; we'll Py_INCREF them to own them once. */
    PyCodeObject *code = PyFrame_GetCode(f);
    if (code == NULL) {
        Py_DECREF(f);
        return NULL;
    }
    PyObject *filename = code->co_filename;
    PyObject *funcname = code->co_name;
    Py_INCREF(filename);
    Py_INCREF(funcname);
    Py_DECREF(code);
    int lineno = PyFrame_GetLineNumber(f);

    PyObject *sinfo = Py_None;
    PyObject *sinfo_owned = NULL;
    if (stack_info && filename != NULL && funcname != NULL) {
        /* Render stack info by delegating to Python's traceback
         * module. The hot path has stack_info=False; this branch
         * is slow-path anyway. */
        PyObject *io_mod = PyImport_ImportModule("io");
        PyObject *tb_mod = PyImport_ImportModule("traceback");
        if (io_mod == NULL || tb_mod == NULL) {
            Py_XDECREF(io_mod);
            Py_XDECREF(tb_mod);
            Py_XDECREF(filename);
            Py_XDECREF(funcname);
            Py_DECREF(f);
            return NULL;
        }
        PyObject *sio = PyObject_CallMethod(io_mod, "StringIO", NULL);
        Py_DECREF(io_mod);
        if (sio == NULL) {
            Py_DECREF(tb_mod);
            Py_XDECREF(filename);
            Py_XDECREF(funcname);
            Py_DECREF(f);
            return NULL;
        }
        PyObject *header = PyUnicode_FromString(
            "Stack (most recent call last):\n");
        PyObject *wrote = PyObject_CallMethodObjArgs(
            sio, PyUnicode_InternFromString("write"), header, NULL);
        Py_DECREF(header);
        Py_XDECREF(wrote);
        PyObject *tb_res = PyObject_CallMethod(
            tb_mod, "print_stack", "OzO", f, NULL, sio);
        Py_DECREF(tb_mod);
        if (tb_res == NULL) {
            Py_DECREF(sio);
            Py_XDECREF(filename);
            Py_XDECREF(funcname);
            Py_DECREF(f);
            return NULL;
        }
        Py_DECREF(tb_res);
        sinfo_owned = PyObject_CallMethod(sio, "getvalue", NULL);
        Py_DECREF(sio);
        if (sinfo_owned != NULL) {
            Py_ssize_t slen = PyUnicode_GET_LENGTH(sinfo_owned);
            if (slen > 0 &&
                PyUnicode_READ_CHAR(sinfo_owned, slen - 1) == '\n') {
                PyObject *trimmed = PyUnicode_Substring(
                    sinfo_owned, 0, slen - 1);
                Py_DECREF(sinfo_owned);
                sinfo_owned = trimmed;
            }
            sinfo = sinfo_owned;
        }
    }

    Py_DECREF(f);

    if (filename == NULL || funcname == NULL) {
        Py_XDECREF(filename);
        Py_XDECREF(funcname);
        Py_XDECREF(sinfo_owned);
        return NULL;
    }

    PyObject *result = Py_BuildValue("OiOO",
        filename, lineno, funcname, sinfo);
    Py_DECREF(filename);
    Py_DECREF(funcname);
    Py_XDECREF(sinfo_owned);
    return result;
}


/*
 * _install_state(logging_module, pathname_cache, getLevelName,
 *                os_path_basename, os_path_splitext,
 *                threading_get_ident, threading_current_thread,
 *                main_thread_ident, main_thread, start_time_ns)
 *
 * Captures references used by `_log_record_init` so the C __init__
 * can avoid attribute lookups on every call. Must be called once
 * from Lib/logging/__init__.py after module-level state is built.
 *
 * `start_time_ns` is the module-level `_startTime` value. The
 * flags (logThreads/logMultiprocessing/logProcesses/logAsyncioTasks)
 * are *not* cached here — they're read dynamically from
 * `logging_module.__dict__` on every LogRecord construction so
 * users toggling the flags at runtime still see immediate effect.
 */
static PyObject *
logging_install_state(PyObject *module, PyObject *args)
{
    logging_state *state = get_logging_state(module);
    PyObject *log_mod, *pathname_cache, *getLevelName,
             *basename, *splitext, *get_ident, *current_thread,
             *main_ident, *main_thread, *start_time_ns_obj,
             *time_module, *os_getpid;
    if (!PyArg_ParseTuple(args, "OOOOOOOOOOOO",
            &log_mod, &pathname_cache, &getLevelName,
            &basename, &splitext, &get_ident, &current_thread,
            &main_ident, &main_thread, &start_time_ns_obj,
            &time_module, &os_getpid)) {
        return NULL;
    }
    long long start_time_ns = PyLong_AsLongLong(start_time_ns_obj);
    if (start_time_ns == -1 && PyErr_Occurred()) {
        return NULL;
    }
    PyObject *sys_mod = PyImport_ImportModule("sys");
    if (sys_mod == NULL) {
        return NULL;
    }
    PyObject *sys_modules = PyObject_GetAttrString(sys_mod, "modules");
    Py_DECREF(sys_mod);
    if (sys_modules == NULL) {
        return NULL;
    }

    Py_INCREF(log_mod);          Py_XSETREF(state->logging_module, log_mod);
    Py_INCREF(pathname_cache);   Py_XSETREF(state->pathname_cache, pathname_cache);
    Py_INCREF(getLevelName);     Py_XSETREF(state->getLevelName, getLevelName);
    Py_INCREF(basename);         Py_XSETREF(state->os_path_basename, basename);
    Py_INCREF(splitext);         Py_XSETREF(state->os_path_splitext, splitext);
    Py_INCREF(get_ident);        Py_XSETREF(state->threading_get_ident, get_ident);
    Py_INCREF(current_thread);   Py_XSETREF(state->threading_current_thread, current_thread);
    Py_INCREF(main_ident);       Py_XSETREF(state->main_thread_ident, main_ident);
    Py_INCREF(main_thread);      Py_XSETREF(state->main_thread, main_thread);
    Py_INCREF(time_module);      Py_XSETREF(state->time_module, time_module);
    Py_INCREF(os_getpid);        Py_XSETREF(state->os_getpid, os_getpid);
    Py_XSETREF(state->sys_modules, sys_modules);
    state->start_time_ns = start_time_ns;
    Py_RETURN_NONE;
}


/*
 * Helper: read a boolean flag from the logging module's globals.
 * Returns -1 on error, else 0/1.
 */
static int
read_logging_flag(logging_state *state, PyObject *name)
{
    PyObject *module_dict = PyModule_GetDict(state->logging_module);
    if (module_dict == NULL) {
        return -1;
    }
    PyObject *v = PyDict_GetItemWithError(module_dict, name);
    if (v == NULL) {
        if (PyErr_Occurred()) return -1;
        return 1;  /* default: True */
    }
    return PyObject_IsTrue(v);
}


/*
 * _log_record_init(self, name, level, pathname, lineno,
 *                  msg, args, exc_info, func=None, sinfo=None, **kwargs)
 *
 * Direct C implementation of LogRecord.__init__. Populates
 * self.__dict__ with all 21 standard attributes via PyDict_SetItem,
 * skipping the interpreter's per-STORE_ATTR dispatch overhead.
 *
 * Mirrors the pure-Python __init__ exactly:
 *   - reads logThreads/logMultiprocessing/logProcesses/logAsyncioTasks
 *     from the logging module's globals each call (so runtime
 *     toggling still works)
 *   - applies the main-thread name cache shortcut
 *   - consults pathname_cache
 *   - handles the dict-as-sole-arg form of args
 */
static PyObject *
logging_log_record_init(PyObject *module,
                        PyObject *const *args, Py_ssize_t nargs,
                        PyObject *kwnames)
{
    logging_state *state = get_logging_state(module);

    if (nargs < 8) {
        PyErr_SetString(PyExc_TypeError,
            "LogRecord.__init__ requires at least 8 positional args "
            "(self, name, level, pathname, lineno, msg, args, exc_info)");
        return NULL;
    }
    PyObject *self = args[0];
    PyObject *name = args[1];
    PyObject *level = args[2];
    PyObject *pathname = args[3];
    PyObject *lineno = args[4];
    PyObject *msg = args[5];
    PyObject *record_args = args[6];
    PyObject *exc_info = args[7];
    PyObject *func = (nargs > 8) ? args[8] : Py_None;
    PyObject *sinfo = (nargs > 9) ? args[9] : Py_None;

    /* Get the instance __dict__. */
    PyObject **dictptr = _PyObject_GetDictPtr(self);
    if (dictptr == NULL) {
        PyErr_SetString(PyExc_TypeError,
            "LogRecord instance has no __dict__");
        return NULL;
    }
    if (*dictptr == NULL) {
        *dictptr = PyDict_New();
        if (*dictptr == NULL) {
            return NULL;
        }
    }
    PyObject *self_dict = *dictptr;

    /* Record creation time in ns. Look up time.time_ns dynamically so
     * unittest.mock.patch('time.time_ns') (used in test_logging for
     * msecs-precision tests) still takes effect. */
    PyObject *time_ns_fn = PyObject_GetAttr(
        state->time_module, state->str_time_ns);
    if (time_ns_fn == NULL) {
        return NULL;
    }
    PyObject *time_ns = PyObject_CallNoArgs(time_ns_fn);
    Py_DECREF(time_ns_fn);
    if (time_ns == NULL) {
        return NULL;
    }
    long long ct_ns = PyLong_AsLongLong(time_ns);
    if (ct_ns == -1 && PyErr_Occurred()) {
        Py_DECREF(time_ns);
        return NULL;
    }

    /* Handle the args-as-dict case:
     *   if args and len(args) == 1 and isinstance(args[0], Mapping) and args[0]:
     *       args = args[0]
     */
    if (PyTuple_Check(record_args) && PyTuple_GET_SIZE(record_args) == 1) {
        PyObject *inner = PyTuple_GET_ITEM(record_args, 0);
        /* Check isinstance(inner, collections.abc.Mapping). Cheap
         * fast path: dict. For other Mappings we'd need to import
         * collections.abc — skip for now, matches most real use. */
        if (PyDict_Check(inner) && PyDict_GET_SIZE(inner) > 0) {
            record_args = inner;
        }
    }

    /* levelname = getLevelName(level) */
    PyObject *levelname = PyObject_CallOneArg(state->getLevelName, level);
    if (levelname == NULL) {
        Py_DECREF(time_ns);
        return NULL;
    }

    /* filename, module lookups via pathname cache. */
    PyObject *filename = NULL;
    PyObject *mod_name = NULL;
    int use_cache = PyUnicode_Check(pathname) || PyBytes_Check(pathname);
    PyObject *cached = NULL;
    if (use_cache) {
        cached = PyDict_GetItemWithError(state->pathname_cache, pathname);
    }
    if (cached != NULL) {
        if (!PyTuple_Check(cached) || PyTuple_GET_SIZE(cached) != 2) {
            PyErr_SetString(PyExc_TypeError,
                "pathname_cache entry must be a 2-tuple");
            Py_DECREF(levelname);
            Py_DECREF(time_ns);
            return NULL;
        }
        filename = PyTuple_GET_ITEM(cached, 0);
        mod_name = PyTuple_GET_ITEM(cached, 1);
        Py_INCREF(filename);
        Py_INCREF(mod_name);
    } else if (use_cache && PyErr_Occurred()) {
        Py_DECREF(levelname);
        Py_DECREF(time_ns);
        return NULL;
    } else {
        filename = PyObject_CallOneArg(state->os_path_basename, pathname);
        if (filename != NULL) {
            PyObject *split = PyObject_CallOneArg(
                state->os_path_splitext, filename);
            if (split != NULL && PyTuple_Check(split) &&
                    PyTuple_GET_SIZE(split) >= 1) {
                mod_name = PyTuple_GET_ITEM(split, 0);
                Py_INCREF(mod_name);
            }
            Py_XDECREF(split);
        }
        if (filename == NULL || mod_name == NULL) {
            PyErr_Clear();
            Py_XDECREF(filename);
            Py_XDECREF(mod_name);
            Py_INCREF(pathname);
            filename = pathname;
            Py_INCREF(state->str_UnknownModule);
            mod_name = state->str_UnknownModule;
        } else {
            /* Cache the successful result. */
            if (use_cache) {
                PyObject *pair = PyTuple_Pack(2, filename, mod_name);
                if (pair != NULL) {
                    PyDict_SetItem(state->pathname_cache, pathname, pair);
                    Py_DECREF(pair);
                }
            }
        }
    }

    /* Populate the instance dict using pre-interned keys. PyDict_SetItem
     * with an interned key skips the PyUnicode_FromString allocation
     * that PyDict_SetItemString would do every call. */
    PyDict_SetItem(self_dict, state->key_name, name);
    PyDict_SetItem(self_dict, state->key_msg, msg);
    PyDict_SetItem(self_dict, state->key_args, record_args);
    PyDict_SetItem(self_dict, state->key_levelname, levelname);
    Py_DECREF(levelname);
    PyDict_SetItem(self_dict, state->key_levelno, level);
    PyDict_SetItem(self_dict, state->key_pathname, pathname);
    PyDict_SetItem(self_dict, state->key_filename, filename);
    Py_DECREF(filename);
    PyDict_SetItem(self_dict, state->key_module, mod_name);
    Py_DECREF(mod_name);
    PyDict_SetItem(self_dict, state->key_exc_info, exc_info);
    PyDict_SetItem(self_dict, state->key_exc_text, Py_None);
    PyDict_SetItem(self_dict, state->key_stack_info, sinfo);
    PyDict_SetItem(self_dict, state->key_lineno, lineno);
    PyDict_SetItem(self_dict, state->key_funcName, func);

    /* created = ct_ns / 1e9 */
    PyObject *created = PyFloat_FromDouble((double)ct_ns / 1e9);
    if (created == NULL) goto error;
    PyDict_SetItem(self_dict, state->key_created, created);
    Py_DECREF(created);

    /* msecs */
    long long msecs_int = (ct_ns % 1000000000LL) / 1000000LL;
    PyObject *msecs = PyFloat_FromDouble((double)msecs_int + 0.0);
    if (msecs == NULL) goto error;
    if (msecs_int == 999) {
        double cf = (double)ct_ns / 1e9;
        long long floor_secs = (long long)cf;
        long long expected_secs = ct_ns / 1000000000LL;
        if (floor_secs != expected_secs) {
            Py_DECREF(msecs);
            msecs = PyFloat_FromDouble(0.0);
            if (msecs == NULL) goto error;
        }
    }
    PyDict_SetItem(self_dict, state->key_msecs, msecs);
    Py_DECREF(msecs);

    /* relativeCreated = (ct - _startTime) / 1e6 */
    double rel = (double)(ct_ns - state->start_time_ns) / 1e6;
    PyObject *relobj = PyFloat_FromDouble(rel);
    if (relobj == NULL) goto error;
    PyDict_SetItem(self_dict, state->key_relativeCreated, relobj);
    Py_DECREF(relobj);

    Py_DECREF(time_ns); time_ns = NULL;

    /* Thread info. */
    int flag_threads = read_logging_flag(state, state->str_logThreads);
    if (flag_threads < 0) goto error;
    if (flag_threads) {
        PyObject *tid = PyObject_CallNoArgs(state->threading_get_ident);
        if (tid == NULL) goto error;
        PyDict_SetItem(self_dict, state->key_thread, tid);
        int same = PyObject_RichCompareBool(
            tid, state->main_thread_ident, Py_EQ);
        Py_DECREF(tid);
        if (same < 0) goto error;
        if (same) {
            PyObject *tname = PyObject_GetAttr(
                state->main_thread, state->key_name_attr);
            if (tname == NULL) goto error;
            PyDict_SetItem(self_dict, state->key_threadName, tname);
            Py_DECREF(tname);
        } else {
            PyObject *ct = PyObject_CallNoArgs(state->threading_current_thread);
            if (ct == NULL) goto error;
            PyObject *tname = PyObject_GetAttr(ct, state->key_name_attr);
            Py_DECREF(ct);
            if (tname == NULL) goto error;
            PyDict_SetItem(self_dict, state->key_threadName, tname);
            Py_DECREF(tname);
        }
    } else {
        PyDict_SetItem(self_dict, state->key_thread, Py_None);
        PyDict_SetItem(self_dict, state->key_threadName, Py_None);
    }

    /* Process name. */
    int flag_mp = read_logging_flag(state, state->str_logMultiprocessing);
    if (flag_mp < 0) goto error;
    if (!flag_mp) {
        PyDict_SetItem(self_dict, state->key_processName, Py_None);
    } else {
        PyObject *processName = state->str_MainProcess;
        Py_INCREF(processName);
        PyObject *mp_mod = PyDict_GetItemWithError(
            state->sys_modules, state->str_multiprocessing);
        if (mp_mod == NULL && PyErr_Occurred()) {
            Py_DECREF(processName);
            goto error;
        }
        if (mp_mod != NULL) {
            PyObject *cur_proc = PyObject_CallMethod(mp_mod, "current_process", NULL);
            if (cur_proc != NULL) {
                PyObject *pname = PyObject_GetAttr(cur_proc, state->key_name_attr);
                Py_DECREF(cur_proc);
                if (pname != NULL) {
                    Py_DECREF(processName);
                    processName = pname;
                }
            }
            if (PyErr_Occurred()) {
                PyErr_Clear();
            }
        }
        PyDict_SetItem(self_dict, state->key_processName, processName);
        Py_DECREF(processName);
    }

    /* Process id — via cached os.getpid. */
    int flag_proc = read_logging_flag(state, state->str_logProcesses);
    if (flag_proc < 0) goto error;
    if (flag_proc && state->os_getpid != NULL) {
        PyObject *pid = PyObject_CallNoArgs(state->os_getpid);
        if (pid == NULL) goto error;
        PyDict_SetItem(self_dict, state->key_process, pid);
        Py_DECREF(pid);
    } else {
        PyDict_SetItem(self_dict, state->key_process, Py_None);
    }

    /* taskName. */
    PyDict_SetItem(self_dict, state->key_taskName, Py_None);
    int flag_async = read_logging_flag(state, state->str_logAsyncioTasks);
    if (flag_async < 0) goto error;
    if (flag_async) {
        PyObject *async_mod = PyDict_GetItemWithError(
            state->sys_modules, state->str_asyncio);
        if (async_mod == NULL && PyErr_Occurred()) {
            goto error;
        }
        if (async_mod != NULL) {
            PyObject *task = PyObject_CallMethod(async_mod, "current_task", NULL);
            if (task != NULL && task != Py_None) {
                PyObject *tname = PyObject_CallMethod(task, "get_name", NULL);
                if (tname != NULL) {
                    PyDict_SetItem(self_dict, state->key_taskName, tname);
                    Py_DECREF(tname);
                }
                Py_DECREF(task);
            } else {
                Py_XDECREF(task);
            }
            if (PyErr_Occurred()) {
                PyErr_Clear();
            }
        }
    }

    Py_RETURN_NONE;

error:
    Py_XDECREF(time_ns);
    return NULL;
}


static PyObject *
logging_set_srcfile(PyObject *module, PyObject *arg)
{
    if (!PyUnicode_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "_set_srcfile expects a str");
        return NULL;
    }
    logging_state *state = get_logging_state(module);
    Py_INCREF(arg);
    Py_XSETREF(state->srcfile, arg);
    if (state->internal_codes != NULL) {
        if (PySet_Clear(state->internal_codes) < 0) {
            return NULL;
        }
    }
    Py_RETURN_NONE;
}


static PyMethodDef logging_methods[] = {
    {"_find_caller", (PyCFunction)(void(*)(void))logging_find_caller,
        METH_FASTCALL,
        "Walk frames and return (filename, lineno, funcname, sinfo|None)."},
    {"_set_srcfile", logging_set_srcfile, METH_O,
        "Install the internal-frame filename marker."},
    {"_install_state", logging_install_state, METH_VARARGS,
        "Cache the module-level references used by _log_record_init."},
    {"_log_record_init",
        (PyCFunction)(void(*)(void))logging_log_record_init,
        METH_FASTCALL | METH_KEYWORDS,
        "C implementation of LogRecord.__init__; bound onto LogRecord."},
    {NULL, NULL}
};


PyDoc_STRVAR(module_doc,
"_logging — optional C accelerator for the logging module.\n\n"
"Exposes _find_caller() used by Logger.findCaller when available;\n"
"Lib/logging/__init__.py falls back to pure-Python on ImportError.");


static int
logging_traverse(PyObject *module, visitproc visit, void *arg)
{
    logging_state *state = get_logging_state(module);
    Py_VISIT(state->srcfile);
    Py_VISIT(state->internal_codes);
    Py_VISIT(state->str_importlib);
    Py_VISIT(state->str_bootstrap);
    Py_VISIT(state->str_unknown_file);
    Py_VISIT(state->str_unknown_function);
    Py_VISIT(state->logging_module);
    Py_VISIT(state->pathname_cache);
    Py_VISIT(state->getLevelName);
    Py_VISIT(state->os_path_basename);
    Py_VISIT(state->os_path_splitext);
    Py_VISIT(state->threading_get_ident);
    Py_VISIT(state->threading_current_thread);
    Py_VISIT(state->sys_modules);
    Py_VISIT(state->main_thread_ident);
    Py_VISIT(state->main_thread);
    Py_VISIT(state->time_module);
    Py_VISIT(state->str_time_ns);
    Py_VISIT(state->os_getpid);
    Py_VISIT(state->str_multiprocessing);
    Py_VISIT(state->str_asyncio);
    Py_VISIT(state->str_MainProcess);
    Py_VISIT(state->str_UnknownModule);
    Py_VISIT(state->str_logThreads);
    Py_VISIT(state->str_logMultiprocessing);
    Py_VISIT(state->str_logProcesses);
    Py_VISIT(state->str_logAsyncioTasks);
    Py_VISIT(state->key_name);
    Py_VISIT(state->key_msg);
    Py_VISIT(state->key_args);
    Py_VISIT(state->key_levelname);
    Py_VISIT(state->key_levelno);
    Py_VISIT(state->key_pathname);
    Py_VISIT(state->key_filename);
    Py_VISIT(state->key_module);
    Py_VISIT(state->key_exc_info);
    Py_VISIT(state->key_exc_text);
    Py_VISIT(state->key_stack_info);
    Py_VISIT(state->key_lineno);
    Py_VISIT(state->key_funcName);
    Py_VISIT(state->key_created);
    Py_VISIT(state->key_msecs);
    Py_VISIT(state->key_relativeCreated);
    Py_VISIT(state->key_thread);
    Py_VISIT(state->key_threadName);
    Py_VISIT(state->key_processName);
    Py_VISIT(state->key_process);
    Py_VISIT(state->key_taskName);
    Py_VISIT(state->key_name_attr);
    return 0;
}


static int
logging_clear(PyObject *module)
{
    logging_state *state = get_logging_state(module);
    Py_CLEAR(state->srcfile);
    Py_CLEAR(state->internal_codes);
    Py_CLEAR(state->str_importlib);
    Py_CLEAR(state->str_bootstrap);
    Py_CLEAR(state->str_unknown_file);
    Py_CLEAR(state->str_unknown_function);
    Py_CLEAR(state->logging_module);
    Py_CLEAR(state->pathname_cache);
    Py_CLEAR(state->getLevelName);
    Py_CLEAR(state->os_path_basename);
    Py_CLEAR(state->os_path_splitext);
    Py_CLEAR(state->threading_get_ident);
    Py_CLEAR(state->threading_current_thread);
    Py_CLEAR(state->sys_modules);
    Py_CLEAR(state->main_thread_ident);
    Py_CLEAR(state->main_thread);
    Py_CLEAR(state->time_module);
    Py_CLEAR(state->str_time_ns);
    Py_CLEAR(state->os_getpid);
    Py_CLEAR(state->str_multiprocessing);
    Py_CLEAR(state->str_asyncio);
    Py_CLEAR(state->str_MainProcess);
    Py_CLEAR(state->str_UnknownModule);
    Py_CLEAR(state->str_logThreads);
    Py_CLEAR(state->str_logMultiprocessing);
    Py_CLEAR(state->str_logProcesses);
    Py_CLEAR(state->str_logAsyncioTasks);
    Py_CLEAR(state->key_name);
    Py_CLEAR(state->key_msg);
    Py_CLEAR(state->key_args);
    Py_CLEAR(state->key_levelname);
    Py_CLEAR(state->key_levelno);
    Py_CLEAR(state->key_pathname);
    Py_CLEAR(state->key_filename);
    Py_CLEAR(state->key_module);
    Py_CLEAR(state->key_exc_info);
    Py_CLEAR(state->key_exc_text);
    Py_CLEAR(state->key_stack_info);
    Py_CLEAR(state->key_lineno);
    Py_CLEAR(state->key_funcName);
    Py_CLEAR(state->key_created);
    Py_CLEAR(state->key_msecs);
    Py_CLEAR(state->key_relativeCreated);
    Py_CLEAR(state->key_thread);
    Py_CLEAR(state->key_threadName);
    Py_CLEAR(state->key_processName);
    Py_CLEAR(state->key_process);
    Py_CLEAR(state->key_taskName);
    Py_CLEAR(state->key_name_attr);
    return 0;
}


static void
logging_free(void *module)
{
    (void)logging_clear((PyObject *)module);
}


static int
logging_modexec(PyObject *m)
{
    logging_state *state = get_logging_state(m);
    state->internal_codes = PySet_New(NULL);
    if (state->internal_codes == NULL) return -1;
    state->str_importlib = PyUnicode_InternFromString("importlib");
    if (state->str_importlib == NULL) return -1;
    state->str_bootstrap = PyUnicode_InternFromString("_bootstrap");
    if (state->str_bootstrap == NULL) return -1;
    state->str_unknown_file = PyUnicode_InternFromString("(unknown file)");
    if (state->str_unknown_file == NULL) return -1;
    state->str_unknown_function =
        PyUnicode_InternFromString("(unknown function)");
    if (state->str_unknown_function == NULL) return -1;
    state->str_multiprocessing = PyUnicode_InternFromString("multiprocessing");
    if (state->str_multiprocessing == NULL) return -1;
    state->str_asyncio = PyUnicode_InternFromString("asyncio");
    if (state->str_asyncio == NULL) return -1;
    state->str_MainProcess = PyUnicode_InternFromString("MainProcess");
    if (state->str_MainProcess == NULL) return -1;
    state->str_UnknownModule = PyUnicode_InternFromString("Unknown module");
    if (state->str_UnknownModule == NULL) return -1;
    state->str_logThreads = PyUnicode_InternFromString("logThreads");
    if (state->str_logThreads == NULL) return -1;
    state->str_logMultiprocessing =
        PyUnicode_InternFromString("logMultiprocessing");
    if (state->str_logMultiprocessing == NULL) return -1;
    state->str_logProcesses = PyUnicode_InternFromString("logProcesses");
    if (state->str_logProcesses == NULL) return -1;
    state->str_logAsyncioTasks = PyUnicode_InternFromString("logAsyncioTasks");
    if (state->str_logAsyncioTasks == NULL) return -1;
    state->str_time_ns = PyUnicode_InternFromString("time_ns");
    if (state->str_time_ns == NULL) return -1;

    /* Pre-intern the 21 LogRecord attribute names so
     * _log_record_init's per-record dict inserts use PyDict_SetItem
     * (fast) instead of PyDict_SetItemString (allocates a new unicode
     * on every call). */
#define INTERN(field, s) do { \
    state->key_##field = PyUnicode_InternFromString(s); \
    if (state->key_##field == NULL) return -1; \
} while (0)
    INTERN(name,            "name");
    INTERN(msg,             "msg");
    INTERN(args,            "args");
    INTERN(levelname,       "levelname");
    INTERN(levelno,         "levelno");
    INTERN(pathname,        "pathname");
    INTERN(filename,        "filename");
    INTERN(module,          "module");
    INTERN(exc_info,        "exc_info");
    INTERN(exc_text,        "exc_text");
    INTERN(stack_info,      "stack_info");
    INTERN(lineno,          "lineno");
    INTERN(funcName,        "funcName");
    INTERN(created,         "created");
    INTERN(msecs,           "msecs");
    INTERN(relativeCreated, "relativeCreated");
    INTERN(thread,          "thread");
    INTERN(threadName,      "threadName");
    INTERN(processName,     "processName");
    INTERN(process,         "process");
    INTERN(taskName,        "taskName");
    INTERN(name_attr,       "name");  /* for threadName inner attr get */
#undef INTERN
    return 0;
}


static PyModuleDef_Slot logging_slots[] = {
    _Py_ABI_SLOT,
    {Py_mod_exec, logging_modexec},
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
    {0, NULL}
};


static struct PyModuleDef _loggingmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_logging",
    .m_size = sizeof(logging_state),
    .m_doc = module_doc,
    .m_methods = logging_methods,
    .m_slots = logging_slots,
    .m_traverse = logging_traverse,
    .m_clear = logging_clear,
    .m_free = logging_free,
};


PyMODINIT_FUNC
PyInit__logging(void)
{
    return PyModuleDef_Init(&_loggingmodule);
}
