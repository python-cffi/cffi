/*
 * wchar_t helpers
 */

#if (Py_UNICODE_SIZE == 2) && (SIZEOF_WCHAR_T == 4)
# define CONVERT_WCHAR_TO_SURROGATES
#endif


#if PY_VERSION_HEX < 0x02070000 && defined(CONVERT_WCHAR_TO_SURROGATES)

/* Before Python 2.7, PyUnicode_FromWideChar is not able to convert
   wchar_t values greater than 65535 into two-unicode-characters surrogates.
*/
static PyObject *
_my_PyUnicode_FromWideChar(register const wchar_t *w,
                           Py_ssize_t size)
{
    PyObject *unicode;
    register Py_ssize_t i;
    Py_ssize_t alloc;
    const wchar_t *orig_w;

    if (w == NULL) {
        PyErr_BadInternalCall();
        return NULL;
    }

    alloc = size;
    orig_w = w;
    for (i = size; i > 0; i--) {
        if (*w > 0xFFFF)
            alloc++;
        w++;
    }
    w = orig_w;
    unicode = PyUnicode_FromUnicode(NULL, alloc);
    if (!unicode)
        return NULL;

    /* Copy the wchar_t data into the new object */
    {
        register Py_UNICODE *u;
        u = PyUnicode_AS_UNICODE(unicode);
        for (i = size; i > 0; i--) {
            if (*w > 0xFFFF) {
                wchar_t ordinal = *w++;
                ordinal -= 0x10000;
                *u++ = 0xD800 | (ordinal >> 10);
                *u++ = 0xDC00 | (ordinal & 0x3FF);
            }
            else
                *u++ = *w++;
        }
    }
    return unicode;
}

#else

# define _my_PyUnicode_FromWideChar PyUnicode_FromWideChar

#endif


static int _my_PyUnicode_AsSingleWideChar(PyObject *unicode, wchar_t *result)
{
    Py_UNICODE *u = PyUnicode_AS_UNICODE(unicode);
    if (PyUnicode_GET_SIZE(unicode) == 1) {
        *result = (wchar_t)(u[0]);
        return 0;
    }
#ifdef CONVERT_WCHAR_TO_SURROGATES
    if (PyUnicode_GET_SIZE(unicode) == 2 &&
            0xD800 <= u[0] && u[0] <= 0xDBFF &&
            0xDC00 <= u[1] && u[1] <= 0xDFFF) {
        *result = 0x10000 + ((u[0] - 0xD800) << 10) + (u[1] - 0xDC00);
        return 0;
    }
#endif
    return -1;
}
