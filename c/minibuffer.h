
/* Implementation of a C object with the 'buffer' or 'memoryview'
 * interface at C-level (as approriate for the version of Python we're
 * compiling for), but only a minimal but *consistent* part of the
 * 'buffer' interface at application level.
 */

typedef struct {
    PyObject_HEAD
    char      *mb_data;
    Py_ssize_t mb_size;
} MiniBufferObj;

static Py_ssize_t mb_length(MiniBufferObj *self)
{
    return self->mb_size;
}

static PyObject *mb_item(MiniBufferObj *self, Py_ssize_t idx)
{
    if (idx < 0 || idx >= self->mb_size ) {
        PyErr_SetString(PyExc_IndexError, "buffer index out of range");
        return NULL;
    }
    return PyBytes_FromStringAndSize(self->mb_data + idx, 1);
}

static PyObject *mb_slice(MiniBufferObj *self,
                          Py_ssize_t left, Py_ssize_t right)
{
    Py_ssize_t size = self->mb_size;
    if (left < 0)     left = 0;
    if (right > size) right = size;
    if (left > right) left = right;
    return PyString_FromStringAndSize(self->mb_data + left, right - left);
}

static int mb_ass_item(MiniBufferObj *self, Py_ssize_t idx, PyObject *other)
{
    if (idx < 0 || idx >= self->mb_size) {
        PyErr_SetString(PyExc_IndexError,
                        "buffer assignment index out of range");
        return -1;
    }
    if (PyBytes_Check(other) && PyBytes_GET_SIZE(other) == 1) {
        self->mb_data[idx] = PyBytes_AS_STRING(other)[0];
        return 0;
    }
    else {
        PyErr_Format(PyExc_TypeError,
                     "must assign a "STR_OR_BYTES
                     " of length 1, not %.200s", Py_TYPE(other)->tp_name);
        return -1;
    }
}

static int mb_ass_slice(MiniBufferObj *self,
                        Py_ssize_t left, Py_ssize_t right, PyObject *other)
{
    const void *buffer;
    Py_ssize_t buffer_len, count;
    Py_ssize_t size = self->mb_size;

    if (PyObject_AsReadBuffer(other, &buffer, &buffer_len) < 0)
        return -1;

    if (left < 0)     left = 0;
    if (right > size) right = size;
    if (left > right) left = right;

    count = right - left;
    if (count != buffer_len) {
        PyErr_SetString(PyExc_ValueError,
                        "right operand length must match slice length");
        return -1;
    }
    memcpy(self->mb_data + left, buffer, count);
    return 0;
}

static Py_ssize_t mb_getdata(MiniBufferObj *self, Py_ssize_t idx, void **pp)
{
    *pp = self->mb_data;
    return self->mb_size;
}

static Py_ssize_t mb_getsegcount(MiniBufferObj *self, Py_ssize_t *lenp)
{
    if (lenp)
        *lenp = self->mb_size;
    return 1;
}

static int mb_getbuf(MiniBufferObj *self, Py_buffer *view, int flags)
{
    return PyBuffer_FillInfo(view, NULL, self->mb_data, self->mb_size,
                             /*readonly=*/0, PyBUF_CONTIG | PyBUF_FORMAT);
}

static PySequenceMethods mb_as_sequence = {
    (lenfunc)mb_length, /*sq_length*/
    (binaryfunc)0, /*sq_concat*/
    (ssizeargfunc)0, /*sq_repeat*/
    (ssizeargfunc)mb_item, /*sq_item*/
    (ssizessizeargfunc)mb_slice, /*sq_slice*/
    (ssizeobjargproc)mb_ass_item, /*sq_ass_item*/
    (ssizessizeobjargproc)mb_ass_slice, /*sq_ass_slice*/
};

static PyBufferProcs mb_as_buffer = {
    (readbufferproc)mb_getdata,
    (writebufferproc)mb_getdata,
    (segcountproc)mb_getsegcount,
    (charbufferproc)mb_getdata,
    (getbufferproc)mb_getbuf,
    (releasebufferproc)0,
};

static PyTypeObject MiniBuffer_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_cffi_backend.buffer",
    sizeof(MiniBufferObj),
    0,
    (destructor)PyObject_Del,                   /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    0,                                          /* tp_repr */
    0,                                          /* tp_as_number */
    &mb_as_sequence,                            /* tp_as_sequence */
    0,                                          /* tp_as_mapping */
    0,                                          /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    PyObject_GenericGetAttr,                    /* tp_getattro */
    0,                                          /* tp_setattro */
    &mb_as_buffer,                              /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GETCHARBUFFER |
        Py_TPFLAGS_HAVE_NEWBUFFER,              /* tp_flags */
};

static PyObject *minibuffer_new(char *data, Py_ssize_t size)
{
    MiniBufferObj *ob = PyObject_New(MiniBufferObj, &MiniBuffer_Type);
    if (ob != NULL) {
        ob->mb_data = data;
        ob->mb_size = size;
    }
    return (PyObject *)ob;
}
