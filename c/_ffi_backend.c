#include <Python.h>
#include <stddef.h>
#include <stdint.h>
#include <dlfcn.h>

/************************************************************/

typedef struct {
    PyObject_HEAD
    void *dl_handle;
} dlobject;

static void dl_dealloc(dlobject *dlobj)
{
    dlclose(dlobj->dl_handle);
    PyObject_Del(dlobj);
}

static PyObject *dl_load_function(dlobject *dlobj, PyObject *args)
{
    /* XXX */
    return NULL;
}

static PyMethodDef dl_methods[] = {
    {"load_function",   (PyCFunction)dl_load_function,  METH_VARARGS},
    {NULL,              NULL}           /* sentinel */
};

static PyTypeObject dl_type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.Library",             /* tp_name */
    sizeof(dlobject),                   /* tp_basicsize */
    0,                                  /* tp_itemsize */
    /* methods */
    (destructor)dl_dealloc,             /* tp_dealloc */
    0,                                  /* tp_print */
    0,                                  /* tp_getattr */
    0,                                  /* tp_setattr */
    0,                                  /* tp_compare */
    0,                                  /* tp_repr */
    0,                                  /* tp_as_number */
    0,                                  /* tp_as_sequence */
    0,                                  /* tp_as_mapping */
    0,                                  /* tp_hash */
    0,                                  /* tp_call */
    0,                                  /* tp_str */
    PyObject_GenericGetAttr,            /* tp_getattro */
    0,                                  /* tp_setattro */
    0,                                  /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                 /* tp_flags */
    0,                                  /* tp_doc */
    0,                                  /* tp_traverse */
    0,                                  /* tp_clear */
    0,                                  /* tp_richcompare */
    0,                                  /* tp_weaklistoffset */
    0,                                  /* tp_iter */
    0,                                  /* tp_iternext */
    dl_methods,                         /* tp_methods */
};

static PyObject *load_library(PyObject *self, PyObject *args)
{
    char *filename;
    void *handle;
    dlobject *dlobj;

    if (!PyArg_ParseTuple(args, "et:load_library",
                          Py_FileSystemDefaultEncoding, &filename))
        return NULL;

    handle = dlopen(filename, RTLD_LAZY);
    if (handle == NULL) {
        char buf[200];
        PyOS_snprintf(buf, sizeof(buf), "cannot load library: %s", filename);
        PyErr_SetString(PyExc_OSError, buf);
        return NULL;
    }

    dlobj = PyObject_New(dlobject, &dl_type);
    if (dlobj == NULL) {
        dlclose(handle);
        return NULL;
    }
    dlobj->dl_handle = handle;
    return (PyObject *)dlobj;
}

/************************************************************/

static PyObject *
nonstandard_integer_types(PyObject *self, PyObject *noarg)
{
    static const int UNSIGNED = 0x1000;
    struct { const char *name; int size; } *ptypes, types[] = {
        { "int8_t",        1 },
        { "uint8_t",       1 | UNSIGNED },
        { "int16_t",       2 },
        { "uint16_t",      2 | UNSIGNED },
        { "int32_t",       4 },
        { "uint32_t",      4 | UNSIGNED },
        { "int64_t",       8 },
        { "uint64_t",      8 | UNSIGNED },

        { "intptr_t",      sizeof(intptr_t) },
        { "uintptr_t",     sizeof(uintptr_t) | UNSIGNED },
        { "ptrdiff_t",     sizeof(ptrdiff_t) },
        { "size_t",        sizeof(size_t) | UNSIGNED },
        { "ssize_t",       sizeof(ssize_t) },
        { "wchar_t",       sizeof(wchar_t) | UNSIGNED },
        { NULL }
    };

    PyObject *d = PyDict_New();
    if (d == NULL)
        return NULL;

    for (ptypes=types; ptypes->name; ptypes++) {
        int err;
        PyObject *obj = PyInt_FromLong(ptypes->size);
        if (obj == NULL)
            goto error;
        err = PyDict_SetItemString(d, ptypes->name, obj);
        Py_DECREF(obj);
        if (err != 0)
            goto error;
    }
    return d;

 error:
    Py_DECREF(d);
    return NULL;
}

static PyMethodDef FFIBackendMethods[] = {
    {"nonstandard_integer_types", nonstandard_integer_types, METH_NOARGS},
    {"load_library", load_library, METH_VARARGS},
    {NULL,     NULL}	/* Sentinel */
};

void init_ffi_backend(void)
{
    PyObject* m;
    m = Py_InitModule("_ffi_backend", FFIBackendMethods);
    if (PyType_Ready(&dl_type) < 0)
        return;
}
