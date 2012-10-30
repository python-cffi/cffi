
/* Emulation of PyFile_Check() and PyFile_AsFile() for Python 3. */

extern PyTypeObject PyIOBase_Type;


#define PyFile_Check(p)  PyObject_IsInstance(p, (PyObject *)&PyIOBase_Type)


void _close_file_capsule(PyObject *ob_capsule)
{
    FILE *f = (FILE *)PyCapsule_GetPointer(ob_capsule, "FILE");
    if (f != NULL)
        fclose(f);
}


static FILE *PyFile_AsFile(PyObject *ob_file)
{
    PyObject *ob, *ob_capsule = NULL, *ob_mode = NULL;
    FILE *f = NULL;
    int fd;
    char *mode;
    _Py_IDENTIFIER(flush);
    _Py_IDENTIFIER(mode);
    _Py_IDENTIFIER(__cffi_FILE);

    ob = _PyObject_CallMethodId(ob_file, &PyId_flush, NULL);
    if (ob == NULL)
        goto fail;
    Py_DECREF(ob);

    ob_capsule = _PyObject_GetAttrId(ob_file, &PyId___cffi_FILE);
    if (ob_capsule == NULL) {
        PyErr_Clear();

        fd = PyObject_AsFileDescriptor(ob_file);
        if (fd < 0)
            goto fail;

        ob_mode = _PyObject_GetAttrId(ob_file, &PyId_mode);
        if (ob_mode == NULL)
            goto fail;
        mode = PyText_AsUTF8(ob_mode);
        if (mode == NULL)
            goto fail;

        fd = dup(fd);
        if (fd < 0) {
            PyErr_SetFromErrno(PyExc_OSError);
            goto fail;
        }

        f = fdopen(fd, mode);
        if (f == NULL) {
            close(fd);
            PyErr_SetFromErrno(PyExc_OSError);
            goto fail;
        }
        setbuf(f, NULL);    /* non-buffered */
        Py_DECREF(ob_mode);
        ob_mode = NULL;

        ob_capsule = PyCapsule_New(f, "FILE", _close_file_capsule);
        if (ob_capsule == NULL) {
            fclose(f);
            goto fail;
        }

        if (_PyObject_SetAttrId(ob_file, &PyId___cffi_FILE, ob_capsule) < 0)
            goto fail;
    }
    return PyCapsule_GetPointer(ob_capsule, "FILE");

 fail:
    Py_XDECREF(ob_mode);
    Py_XDECREF(ob_capsule);
    return NULL;
}
