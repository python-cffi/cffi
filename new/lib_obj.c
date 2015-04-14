
/* A Lib object is what is returned by any of:

   - the "lib" attribute of a C extension module originally created by
     recompile()

   - ffi.dlopen()

   - ffi.verify()

   A Lib object is special in the sense that it has a custom
   __getattr__ which returns C globals, functions and constants.  It
   raises AttributeError for anything else, like '__class__'.

   A Lib object has internally a reference back to the FFI object,
   which holds the _cffi_type_context_s used to create lazily the
   objects returned by __getattr__.  For a dlopen()ed Lib object, all
   the 'address' fields in _cffi_global_s are NULL, and instead
   dlsym() is used lazily on the l_dl_lib.
*/

struct LibObject_s {
    PyObject_HEAD
    PyObject *l_dict;           /* content, built lazily */
    struct FFIObject_s *l_ffi;  /* ffi object */
    void *l_dl_lib;             /* the result of 'dlopen()', or NULL */
};

#define ZefLib_Check(ob)  ((Py_TYPE(ob) == &ZefLib_Type))

static void lib_dealloc(ZefLibObject *lib)
{
    (void)lib_close(lib);
    PyObject_Del(lib);
}

static PyObject *lib_repr(ZefLibObject *lib)
{
    return PyText_FromFormat("<zeffir.Lib object for '%.200s'%s>",
                             lib->l_libname,
                             lib->l_dl_lib == NULL ? " (closed)" : "");
}

static PyObject *lib_findattr(ZefLibObject *lib, PyObject *name, PyObject *exc)
{
    /* does not return a new reference! */

    if (lib->l_dict == NULL) {
        PyErr_Format(ZefError, "lib '%.200s' was closed", lib->l_libname);
        return NULL;
    }

    PyObject *x = PyDict_GetItem(lib->l_dict, name);
    if (x == NULL) {
        PyErr_Format(exc,
                     "lib '%.200s' has no function,"
                     " global variable or constant '%.200s'",
                     lib->l_libname,
                     PyText_Check(name) ? PyText_AS_UTF8(name) : "?");
        return NULL;
    }
    return x;
}

static PyObject *lib_getattr(ZefLibObject *lib, PyObject *name)
{
    PyObject *x = lib_findattr(lib, name, PyExc_AttributeError);
    if (x == NULL)
        return NULL;

    if (ZefGlobSupport_Check(x)) {
        return read_global_var((ZefGlobSupportObject *)x);
    }
    Py_INCREF(x);
    return x;
}

static int lib_setattr(ZefLibObject *lib, PyObject *name, PyObject *val)
{
    PyObject *x = lib_findattr(lib, name, PyExc_AttributeError);
    if (x == NULL)
        return -1;

    if (val == NULL) {
        PyErr_SetString(PyExc_AttributeError,
                        "cannot delete attributes from Lib object");
        return -1;
    }

    if (ZefGlobSupport_Check(x)) {
        return write_global_var((ZefGlobSupportObject *)x, val);
    }

    PyErr_Format(PyExc_AttributeError,
                 "cannot write to function or constant '%.200s'",
                 PyText_Check(name) ? PyText_AS_UTF8(name) : "?");
    return -1;
}

static PyObject *lib_dir(PyObject *lib, PyObject *noarg)
{
    return PyDict_Keys(((ZefLibObject *)lib)->l_dict);
}

static PyMethodDef lib_methods[] = {
    {"__dir__",   lib_dir,  METH_NOARGS},
    {NULL,        NULL}           /* sentinel */
};

static PyTypeObject ZefLib_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "zeffir.Lib",
    sizeof(ZefLibObject),
    0,
    (destructor)lib_dealloc,                    /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    (reprfunc)lib_repr,                         /* tp_repr */
    0,                                          /* tp_as_number */
    0,                                          /* tp_as_sequence */
    0,                                          /* tp_as_mapping */
    0,                                          /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    (getattrofunc)lib_getattr,                  /* tp_getattro */
    (setattrofunc)lib_setattr,                  /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                         /* tp_flags */
    0,                                          /* tp_doc */
    0,                                          /* tp_traverse */
    0,                                          /* tp_clear */
    0,                                          /* tp_richcompare */
    0,                                          /* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    lib_methods,                                /* tp_methods */
    0,                                          /* tp_members */
    0,                                          /* tp_getset */
    0,                                          /* tp_base */
    0,                                          /* tp_dict */
    0,                                          /* tp_descr_get */
    0,                                          /* tp_descr_set */
    offsetof(ZefLibObject, l_dict),             /* tp_dictoffset */
};

static void lib_dlerror(ZefLibObject *lib)
{
    char *error = dlerror();
    if (error == NULL)
        error = "(no error reported)";
    PyErr_Format(PyExc_OSError, "%s: %s", lib->l_libname, error);
}

static ZefLibObject *lib_create(PyObject *path)
{
    ZefLibObject *lib;

    lib = PyObject_New(ZefLibObject, &ZefLib_Type);
    if (lib == NULL)
        return NULL;

    lib->l_dl_lib = NULL;
    lib->l_libname = PyString_AsString(path);
    Py_INCREF(path);
    lib->l_libname_obj = path;
    lib->l_dict = PyDict_New();
    if (lib->l_dict == NULL) {
        Py_DECREF(lib);
        return NULL;
    }

    lib->l_dl_lib = dlopen(lib->l_libname, RTLD_LAZY);
    if (lib->l_dl_lib == NULL) {
        lib_dlerror(lib);
        Py_DECREF(lib);
        return NULL;
    }
    return lib;
}

static int lib_close(ZefLibObject *lib)
{
    void *dl_lib;
    Py_CLEAR(lib->l_dict);

    dl_lib = lib->l_dl_lib;
    if (dl_lib != NULL) {
        lib->l_dl_lib = NULL;
        if (dlclose(dl_lib) != 0) {
            lib_dlerror(lib);
            return -1;
        }
    }
    return 0;
}
