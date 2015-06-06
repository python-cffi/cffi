
/* translated to C from cffi/gc_weakref.py */


static PyObject *gc_wref_remove(PyObject *ffi_wref_tup, PyObject *key)
{
    FFIObject *ffi;
    PyObject *indexobj, *destructor, *cdata, *freelist, *result;
    Py_ssize_t index;

    /* here, tup is a 4-tuple (ffi, destructor, cdata, index) */
    if (!PyTuple_Check(ffi_wref_tup))
        goto oops;    /* should never occur */

    ffi = (FFIObject *)PyTuple_GET_ITEM(ffi_wref_tup, 0);
    destructor = PyTuple_GET_ITEM(ffi_wref_tup, 1);
    cdata = PyTuple_GET_ITEM(ffi_wref_tup, 2);
    indexobj = PyTuple_GET_ITEM(ffi_wref_tup, 3);

    index = PyInt_AsSsize_t(indexobj);
    if (index < 0)
        goto oops;    /* should never occur */

    /* assert gc_wrefs[index] is key */
    if (PyList_GET_ITEM(ffi->gc_wrefs, index) != key)
        goto oops;    /* should never occur */

    /* gc_wrefs[index] = freelist */
    /* transfer ownership of 'freelist' to 'gc_wrefs[index]' */
    freelist = ffi->gc_wrefs_freelist;
    PyList_SET_ITEM(ffi->gc_wrefs, index, freelist);

    /* freelist = index */
    ffi->gc_wrefs_freelist = indexobj;
    Py_INCREF(indexobj);

    /* destructor(cdata) */
    result = PyObject_CallFunctionObjArgs(destructor, cdata, NULL);

    Py_DECREF(key);    /* free the reference that was in 'gc_wrefs[index]' */
    return result;

 oops:
    PyErr_SetString(PyExc_SystemError, "cgc: internal inconsistency");
    /* random leaks may follow */
    return NULL;
}

static PyMethodDef remove_callback = {
    "gc_wref_remove", (PyCFunction)gc_wref_remove, METH_O
};

static PyObject *gc_weakrefs_build(FFIObject *ffi, CDataObject *cdata,
                                   PyObject *destructor)
{
    PyObject *new_cdata, *ref = NULL, *tup = NULL, *remove_fn = NULL;
    Py_ssize_t index;
    PyObject *datalist;

    if (ffi->gc_wrefs == NULL) {
        /* initialize */
        datalist = PyList_New(0);
        if (datalist == NULL)
            return NULL;
        ffi->gc_wrefs = datalist;
        assert(ffi->gc_wrefs_freelist == NULL);
        ffi->gc_wrefs_freelist = Py_None;
        Py_INCREF(Py_None);
    }

    /* new_cdata = self.ffi.cast(typeof(cdata), cdata) */
    new_cdata = do_cast(cdata->c_type, (PyObject *)cdata);
    if (new_cdata == NULL)
        goto error;

    /* if freelist is None: */
    datalist = ffi->gc_wrefs;
    if (ffi->gc_wrefs_freelist == Py_None) {
        /* index = len(gc_wrefs) */
        index = PyList_GET_SIZE(datalist);
        /* gc_wrefs.append(None) */
        if (PyList_Append(datalist, Py_None) < 0)
            goto error;
        tup = Py_BuildValue("OOOn", ffi, destructor, cdata, index);
    }
    else {
        /* index = freelist */
        index = PyInt_AsSsize_t(ffi->gc_wrefs_freelist);
        if (index < 0)
            goto error;   /* should not occur */
        tup = PyTuple_Pack(4, ffi, destructor, cdata, ffi->gc_wrefs_freelist);
    }
    if (tup == NULL)
        goto error;

    remove_fn = PyCFunction_New(&remove_callback, tup);
    if (remove_fn == NULL)
        goto error;

    ref = PyWeakref_NewRef(new_cdata, remove_fn);
    if (ref == NULL)
        goto error;

    /* freelist = gc_wrefs[index] (which is None if we just did append(None)) */
    /* transfer ownership of 'datalist[index]' into gc_wrefs_freelist */
    Py_DECREF(ffi->gc_wrefs_freelist);
    ffi->gc_wrefs_freelist = PyList_GET_ITEM(datalist, index);
    /* gc_wrefs[index] = ref */
    /* transfer ownership of 'ref' into 'datalist[index]' */
    PyList_SET_ITEM(datalist, index, ref);
    Py_DECREF(remove_fn);
    Py_DECREF(tup);

    return new_cdata;

 error:
    Py_XDECREF(new_cdata);
    Py_XDECREF(ref);
    Py_XDECREF(tup);
    Py_XDECREF(remove_fn);
    return NULL;
}
