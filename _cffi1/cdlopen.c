/* ffi.dlopen() interface with dlopen()/dlsym()/dlclose() */

static void *cdlopen_fetch(PyObject *libname, void *libhandle, char *symbol)
{
    void *address;

    if (libhandle == NULL) {
        PyErr_Format(FFIError, "library '%s' has been closed",
                     PyText_AS_UTF8(libname));
        return NULL;
    }

    dlerror();   /* clear error condition */
    address = dlsym(libhandle, symbol);
    if (address == NULL) {
        const char *error = dlerror();
        PyErr_Format(FFIError, "symbol '%s' not found in library '%s': %s",
                     symbol, PyText_AS_UTF8(libname), error);
    }
    return address;
}

static int cdlopen_close(PyObject *libname, void *libhandle)
{
    if (libhandle != NULL && dlclose(libhandle) != 0) {
        const char *error = dlerror();
        PyErr_Format(FFIError, "closing library '%s': %s",
                     PyText_AS_UTF8(libname), error);
        return -1;
    }
    return 0;
}



static PyObject *ffi_dlclose(PyObject *self, PyObject *args)
{
    LibObject *lib;
    if (!PyArg_ParseTuple(args, "O!", &Lib_Type, &lib))
        return NULL;

    if (lib->l_libhandle == NULL) {
        PyErr_Format(FFIError, "library '%s' is already closed "
                     "or was not created with ffi.dlopen()",
                     PyText_AS_UTF8(lib->l_libhandle));
        return NULL;
    }

    if (cdlopen_close(lib->l_libname, lib->l_libhandle) < 0)
        return NULL;

    /* Clear the dict to force further accesses to do cdlopen_fetch()
       again, and fail because the library was closed. */
    PyDict_Clear(lib->l_dict);

    Py_INCREF(Py_None);
    return Py_None;
}
