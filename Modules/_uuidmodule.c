/*
 * Python UUID module that wraps libuuid or Windows rpcrt4.dll.
 * DCE compatible Universally Unique Identifier library.
 */

#ifndef Py_BUILD_CORE_BUILTIN
#  define Py_BUILD_CORE_MODULE 1
#endif

#include "Python.h"
#if defined(HAVE_UUID_H)
  // AIX, FreeBSD, libuuid with pkgconf
  #include <uuid.h>
#elif defined(HAVE_UUID_UUID_H)
  // libuuid without pkgconf
  #include <uuid/uuid.h>
#endif
#ifdef HAVE_ERRNO_H
#  include <errno.h>
#endif
#if defined(HAVE_SYS_RANDOM_H) && (defined(HAVE_GETRANDOM) || defined(HAVE_GETENTROPY))
#  include <sys/random.h>
#endif

#ifdef MS_WINDOWS
#include <rpc.h>
#endif

#if !defined(MS_WINDOWS) && (defined(HAVE_UUID_H) || defined(HAVE_UUID_UUID_H))

static PyObject *
py_uuid_generate_time_safe(PyObject *Py_UNUSED(context),
                           PyObject *Py_UNUSED(ignored))
{
    uuid_t uuid;
#ifdef HAVE_UUID_GENERATE_TIME_SAFE
    int res;

    res = uuid_generate_time_safe(uuid);
    return Py_BuildValue("y#i", (const char *) uuid, sizeof(uuid), res);
#elif defined(HAVE_UUID_CREATE)
    uint32_t status;
    uuid_create(&uuid, &status);
# if defined(HAVE_UUID_ENC_BE)
    unsigned char buf[sizeof(uuid)];
    uuid_enc_be(buf, &uuid);
    return Py_BuildValue("y#i", buf, sizeof(uuid), (int) status);
# else
    return Py_BuildValue("y#i", (const char *) &uuid, sizeof(uuid), (int) status);
# endif /* HAVE_UUID_CREATE */
#else /* HAVE_UUID_GENERATE_TIME_SAFE */
    uuid_generate_time(uuid);
    return Py_BuildValue("y#O", (const char *) uuid, sizeof(uuid), Py_None);
#endif /* HAVE_UUID_GENERATE_TIME_SAFE */
}

#elif defined(MS_WINDOWS)

static PyObject *
py_UuidCreate(PyObject *Py_UNUSED(context),
              PyObject *Py_UNUSED(ignored))
{
    UUID uuid;
    RPC_STATUS res;

    Py_BEGIN_ALLOW_THREADS
    res = UuidCreateSequential(&uuid);
    Py_END_ALLOW_THREADS

    switch (res) {
    case RPC_S_OK:
    case RPC_S_UUID_LOCAL_ONLY:
    case RPC_S_UUID_NO_ADDRESS:
        /*
        All success codes, but the latter two indicate that the UUID is random
        rather than based on the MAC address. If the OS can't figure this out,
        neither can we, so we'll take it anyway.
        */
        return Py_BuildValue("y#", (const char *)&uuid, sizeof(uuid));
    }
    PyErr_SetFromWindowsErr(res);
    return NULL;
}

static int
py_windows_has_stable_node(void)
{
    UUID uuid;
    RPC_STATUS res;
    Py_BEGIN_ALLOW_THREADS
    res = UuidCreateSequential(&uuid);
    Py_END_ALLOW_THREADS
    return res == RPC_S_OK;
}
#endif

#if defined(HAVE_GETRANDOM)
static int
uuid_fill_random_bytes(unsigned char *buffer, Py_ssize_t size)
{
    while (size > 0) {
        ssize_t n = getrandom(buffer, (size_t)size, 0);
        if (n < 0) {
            if (errno == EINTR) {
                continue;
            }
            PyErr_SetFromErrno(PyExc_OSError);
            return -1;
        }
        buffer += n;
        size -= n;
    }
    return 0;
}
#elif defined(HAVE_GETENTROPY)
static int
uuid_fill_random_bytes(unsigned char *buffer, Py_ssize_t size)
{
    while (size > 0) {
        size_t len = (size_t)Py_MIN(size, 256);
        if (getentropy(buffer, len) < 0) {
            if (errno == EINTR) {
                continue;
            }
            PyErr_SetFromErrno(PyExc_OSError);
            return -1;
        }
        buffer += len;
        size -= (Py_ssize_t)len;
    }
    return 0;
}
#endif

#if defined(HAVE_GETRANDOM) || defined(HAVE_GETENTROPY)
static PyObject *
py_uuid_generate_random_int(PyObject *Py_UNUSED(context),
                            PyObject *Py_UNUSED(ignored))
{
    unsigned char uuid[16];

    if (uuid_fill_random_bytes(uuid, sizeof(uuid)) < 0) {
        return NULL;
    }

    // RFC 4122/9562 version and variant bits in big-endian byte order.
    uuid[6] = (uuid[6] & 0x0f) | 0x40;
    uuid[8] = (uuid[8] & 0x3f) | 0x80;

    return _PyLong_FromByteArray(uuid, sizeof(uuid), 0, 0);
}
#endif


static int
uuid_exec(PyObject *module)
{
#define ADD_INT(NAME, VALUE)                                        \
    do {                                                            \
        if (PyModule_AddIntConstant(module, (NAME), (VALUE)) < 0) { \
           return -1;                                               \
        }                                                           \
    } while (0)

#if defined(HAVE_UUID_H) || defined(HAVE_UUID_UUID_H)
    assert(sizeof(uuid_t) == 16);
#endif
#if defined(MS_WINDOWS)
    ADD_INT("has_uuid_generate_time_safe", 0);
#elif defined(HAVE_UUID_GENERATE_TIME_SAFE)
    ADD_INT("has_uuid_generate_time_safe", 1);
#else
    ADD_INT("has_uuid_generate_time_safe", 0);
#endif

#if defined(MS_WINDOWS)
    ADD_INT("has_stable_extractable_node", py_windows_has_stable_node());
#elif defined(HAVE_UUID_GENERATE_TIME_SAFE_STABLE_MAC)
    ADD_INT("has_stable_extractable_node", 1);
#else
    ADD_INT("has_stable_extractable_node", 0);
#endif

#undef ADD_INT
    return 0;
}

static PyMethodDef uuid_methods[] = {
#if defined(HAVE_GETRANDOM) || defined(HAVE_GETENTROPY)
    {"generate_random_int", py_uuid_generate_random_int, METH_NOARGS, NULL},
#endif
#if defined(HAVE_UUID_UUID_H) || defined(HAVE_UUID_H)
    {"generate_time_safe", py_uuid_generate_time_safe, METH_NOARGS, NULL},
#endif
#if defined(MS_WINDOWS)
    {"UuidCreate", py_UuidCreate, METH_NOARGS, NULL},
#endif
    {NULL, NULL, 0, NULL}           /* sentinel */
};

static PyModuleDef_Slot uuid_slots[] = {
    {Py_mod_exec, uuid_exec},
    {Py_mod_multiple_interpreters, Py_MOD_PER_INTERPRETER_GIL_SUPPORTED},
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
    {0, NULL}
};

static struct PyModuleDef uuidmodule = {
    PyModuleDef_HEAD_INIT,
    .m_name = "_uuid",
    .m_size = 0,
    .m_methods = uuid_methods,
    .m_slots = uuid_slots,
};

PyMODINIT_FUNC
PyInit__uuid(void)
{
    return PyModuleDef_Init(&uuidmodule);
}
