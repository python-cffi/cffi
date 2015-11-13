
static void _cffi_call_python(struct _cffi_callpy_s *callpy, char *args)
{
    /* Invoked by the helpers generated from CFFI_CALL_PYTHON in the cdef.

       'callpy' is a static structure that describes which of the
       CFFI_CALL_PYTHON is called.  It has got fields 'name' and
       'type_index' describing the function, and more reserved fields
       that are initially zero.  These reserved fields are set up by
       ffi.call_python(), which invokes init_call_python() below.

       'args' is a pointer to an array of 8-byte entries.  Each entry
       contains an argument.  If an argument is less than 8 bytes, only
       the part at the beginning of the entry is initialized.  If an
       argument is 'long double' or a struct/union, then it is passed
       by reference.

       'args' is also used as the place to write the result to.  In all
       cases, 'args' is at least 8 bytes in size.
    */
    save_errno();
    {
#ifdef WITH_THREAD
    PyGILState_STATE state = PyGILState_Ensure();
#endif
    const struct _cffi_type_context_s *ctx;
    ctx = (const struct _cffi_type_context_s *)callpy->reserved1;

    if (ctx == NULL) {
        /* uninitialized! */
        PyObject *f = PySys_GetObject("stderr");
        if (f != NULL) {
            PyFile_WriteString("CFFI_CALL_PYTHON: function ", f);
            PyFile_WriteString(callpy->name, f);
            PyFile_WriteString("() called, but no code was attached "
                               "to it yet with ffi.call_python('", f);
            PyFile_WriteString(callpy->name, f);
            PyFile_WriteString("').  Returning 0.\n", f);
        }
        memset(args, 0, callpy->size_of_result);
        return;
    }

    abort();

#ifdef WITH_THREAD
    PyGILState_Release(state);
#endif
    }
    restore_errno();
}
