
/* translated to C from cffi/gc_weakref.py */


static PyObject *const_name_pop;

static PyObject *gc_wref_remove(PyObject *ffi_wref_data, PyObject *arg)
{
    PyObject *destructor, *cdata, *x;
    PyObject *res = PyObject_CallMethodObjArgs(ffi_wref_data,
                                               const_name_pop, arg, NULL);
    if (res == NULL)
        return NULL;

    assert(PyTuple_Check(res));
    destructor = PyTuple_GET_ITEM(res, 0);
    cdata = PyTuple_GET_ITEM(res, 1);
    x = PyObject_CallFunctionObjArgs(destructor, cdata, NULL);
    Py_DECREF(res);
    if (x == NULL)
        return NULL;
    Py_DECREF(x);

    Py_INCREF(Py_None);
    return Py_None;
}

static PyMethodDef remove_callback = {
    "gc_wref_remove", (PyCFunction)gc_wref_remove, METH_O
};

static PyObject *gc_weakrefs_build(FFIObject *ffi, CDataObject *cd,
                                   PyObject *destructor)
{
    PyObject *new_cdata, *ref = NULL, *tup = NULL;

    if (ffi->gc_wrefs == NULL) {
        /* initialize */
        PyObject *data;

        if (const_name_pop == NULL) {
            const_name_pop = PyText_InternFromString("pop");
            if (const_name_pop == NULL)
                return NULL;
        }
        data = PyDict_New();
        if (data == NULL)
            return NULL;
        ffi->gc_wrefs = PyCFunction_New(&remove_callback, data);
        Py_DECREF(data);
        if (ffi->gc_wrefs == NULL)
            return NULL;
    }

    new_cdata = do_cast(cd->c_type, (PyObject *)cd);
    if (new_cdata == NULL)
        goto error;

    ref = PyWeakref_NewRef(new_cdata, ffi->gc_wrefs);
    if (ref == NULL)
        goto error;

    tup = PyTuple_Pack(2, destructor, cd);
    if (tup == NULL)
        goto error;

    /* the 'self' of the function 'gc_wrefs' is actually the data dict */
    if (PyDict_SetItem(PyCFunction_GET_SELF(ffi->gc_wrefs), ref, tup) < 0)
        goto error;

    Py_DECREF(tup);
    Py_DECREF(ref);
    return new_cdata;

 error:
    Py_XDECREF(new_cdata);
    Py_XDECREF(ref);
    Py_XDECREF(tup);
    return NULL;
}
