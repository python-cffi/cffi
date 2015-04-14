#include "_cffi_include.h"


int foo42(int a, int *b)
{
    return a - *b;
}

int foo64(int a)
{
    return ~a;
}

/************************************************************/

static void *_cffi_types[] = {
    _CFFI_OP(_CFFI_OP_FUNCTION, 1),
    _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_INT),
    _CFFI_OP(_CFFI_OP_POINTER, 1),
    _CFFI_OP(_CFFI_OP_FUNCTION_END, 0),
    _CFFI_OP(_CFFI_OP_FUNCTION, 1),
    _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_INT),
    _CFFI_OP(_CFFI_OP_FUNCTION_END, 0),
};

static PyObject *
_cffi_f_foo42(PyObject *self, PyObject *args)
{
  int x0;
  int * x1;
  Py_ssize_t datasize;
  int result;
  PyObject *arg0;
  PyObject *arg1;

  if (!PyArg_ParseTuple(args, "OO:foo42", &arg0, &arg1))
    return NULL;

  x0 = _cffi_to_c_int(arg0, int);
  if (x0 == (int)-1 && PyErr_Occurred())
    return NULL;

  datasize = _cffi_prepare_pointer_call_argument(
      _cffi_types[1], arg1, (char **)&x1);
  if (datasize != 0) {
    if (datasize < 0)
      return NULL;
    x1 = alloca(datasize);
    memset((void *)x1, 0, datasize);
    if (_cffi_convert_array_from_object((char *)x1, _cffi_types[1], arg1) < 0)
      return NULL;
  }

  Py_BEGIN_ALLOW_THREADS
  _cffi_restore_errno();
  { result = foo42(x0, x1); }
  _cffi_save_errno();
  Py_END_ALLOW_THREADS

  return _cffi_from_c_int(result, int);
}

static PyObject *
_cffi_f_foo64(PyObject *self, PyObject *arg0)
{
  int x0;
  int result;

  x0 = _cffi_to_c_int(arg0, int);
  if (x0 == (int)-1 && PyErr_Occurred())
    return NULL;

  Py_BEGIN_ALLOW_THREADS
  _cffi_restore_errno();
  { result = foo64(x0); }
  _cffi_save_errno();
  Py_END_ALLOW_THREADS

  return _cffi_from_c_int(result, int);
}

static const struct _cffi_global_s _cffi_globals[] = {
    { "foo42", &_cffi_f_foo42, _CFFI_OP(_CFFI_OP_CPYTHON_BLTN_V, 0) },
    { "foo64", &_cffi_f_foo64, _CFFI_OP(_CFFI_OP_CPYTHON_BLTN_O, 4) },
};

static const struct _cffi_type_context_s _cffi_type_context = {
    _cffi_types,
    _cffi_globals,
    NULL,  /* no constants */
    NULL,
    NULL,
    NULL,
    NULL,
    2,  /* num_globals */
    0,
    0,
    0,
    0,
};

PyMODINIT_FUNC
initmanual(void)
{
    if (_cffi_init() < 0)
        return;

    _cffi_init_module("manual", &_cffi_type_context);
}
