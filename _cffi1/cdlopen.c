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

static void cdlopen_close_ignore_errors(void *libhandle)
{
    if (libhandle != NULL)
        dlclose(libhandle);
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

static PyObject *ffi_dlopen(PyObject *self, PyObject *args)
{
    char *filename_or_null, *printable_filename;
    void *handle;
    int flags = 0;

    if (PyTuple_GET_SIZE(args) == 0 || PyTuple_GET_ITEM(args, 0) == Py_None) {
        PyObject *dummy;
        if (!PyArg_ParseTuple(args, "|Oi:load_library",
                              &dummy, &flags))
            return NULL;
        filename_or_null = NULL;
    }
    else if (!PyArg_ParseTuple(args, "et|i:load_library",
                          Py_FileSystemDefaultEncoding, &filename_or_null,
                          &flags))
        return NULL;

    if ((flags & (RTLD_NOW | RTLD_LAZY)) == 0)
        flags |= RTLD_NOW;
    printable_filename = filename_or_null ? filename_or_null : "<None>";

    handle = dlopen(filename_or_null, flags);
    if (handle == NULL) {
        const char *error = dlerror();
        PyErr_Format(PyExc_OSError, "cannot load library '%s': %s",
                     printable_filename, error);
        return NULL;
    }
    return (PyObject *)lib_internal_new((FFIObject *)self,
                                        printable_filename, handle);
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


static int cdl_int(char *src)
{
    unsigned char *usrc = (unsigned char *)src;
    return (usrc[0] << 24) | (usrc[1] << 16) | (usrc[2] << 8) | usrc[3];
}

static _cffi_opcode_t cdl_opcode(char *src)
{
    return (_cffi_opcode_t)(Py_ssize_t)cdl_int(src);
}

static int ffiobj_init(PyObject *self, PyObject *args, PyObject *kwds)
{
    FFIObject *ffi;
    static char *keywords[] = {"module_name", "_version", "_types",
                               "_globals", "_struct_unions", "_enums",
                               "_typenames", "_consts", NULL};
    char *ffiname = NULL, *types = NULL, *building = NULL;
    Py_ssize_t version = -1;
    Py_ssize_t types_len = 0;
    PyObject *globals = NULL, *struct_unions = NULL, *enums = NULL;
    PyObject *typenames = NULL, *consts = NULL;

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|sns#O!OOOO:FFI", keywords,
                                     &ffiname, &version, &types, &types_len,
                                     &PyTuple_Type, &globals,
                                     &struct_unions, &enums,
                                     &typenames, &consts))
        return -1;

    ffi = (FFIObject *)self;
    if (ffi->ctx_is_nonempty) {
        PyErr_SetString(PyExc_ValueError,
                        "cannot call FFI.__init__() more than once");
        return -1;
    }
    ffi->ctx_is_nonempty = 1;

    if (types_len > 0) {
        _cffi_opcode_t *ntypes;
        Py_ssize_t i, n = types_len / 4;    /* 4 bytes entries */

        building = PyMem_Malloc(n * sizeof(_cffi_opcode_t));
        if (building == NULL)
            goto error;
        ntypes = (_cffi_opcode_t *)building;

        for (i = 0; i < n; i++) {
            ntypes[i] = cdl_opcode(types);
            types += 4;
        }
        ffi->types_builder.ctx.types = ntypes;
        building = NULL;
    }

    if (globals != NULL) {
        struct _cffi_global_s *nglob;
        Py_ssize_t i, n = PyTuple_GET_SIZE(globals);

        building = PyMem_Malloc(n * sizeof(struct _cffi_global_s));
        if (building == NULL)
            goto error;
        memset(building, 0, n * sizeof(struct _cffi_global_s));
        nglob = (struct _cffi_global_s *)building;

        for (i = 0; i < n; i++) {
            char *g = PyString_AS_STRING(PyTuple_GET_ITEM(globals, i));
            nglob[i].type_op = cdl_opcode(g);
            nglob[i].name = g + 4;
        }
        ffi->types_builder.ctx.globals = nglob;
        ffi->types_builder.ctx.num_globals = n;
        building = NULL;
    }

    if (consts != NULL) {
        Py_INCREF(consts);
        ffi->types_builder.known_constants = consts;
    }

    /* Above, we took directly some "char *" strings out of the strings,
       typically from somewhere inside tuples.  Keep them alive by
       incref'ing the whole input arguments. */
    Py_INCREF(args);
    Py_XINCREF(kwds);
    ffi->types_builder._keepalive1 = args;
    ffi->types_builder._keepalive2 = kwds;
    return 0;

 error:
    if (building != NULL)
        PyMem_Free(building);
    if (!PyErr_Occurred())
        PyErr_NoMemory();
    return -1;
}
