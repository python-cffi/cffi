#include <Python.h>
#include "parse_c_type.h"


static PyObject *all_primitives[_CFFI__NUM_PRIM];


PyObject *build_primitive_type(int num)
{
    PyObject *x;

    switch (num) {

    case _CFFI_PRIM_VOID:
        x = PyString_FromString("VOID");
        break;

    case _CFFI_PRIM_INT:
        x = PyString_FromString("INT");
        break;

    default:
        PyErr_Format(PyExc_NotImplementedError, "prim=%d", num);
        return NULL;
    }

    all_primitives[num] = x;
    return x;
}


PyObject *realize_c_type(struct _cffi_type_context_s *ctx,
                         _cffi_opcode_t opcodes[], int index)
{
    PyObject *x, *y;
    _cffi_opcode_t op = opcodes[index];

    switch (_CFFI_GETOP(op)) {

    case _CFFI_OP_PRIMITIVE:
        x = all_primitives[_CFFI_GETARG(op)];
        if (x == NULL)
            x = build_primitive_type(_CFFI_GETARG(op));
        Py_XINCREF(x);
        return x;

    case _CFFI_OP_POINTER:
        y = realize_c_type(ctx, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        x = Py_BuildValue("sO", "pointer", y);
        Py_DECREF(y);
        return x;

    default:
        PyErr_Format(PyExc_NotImplementedError, "op=%d", (int)_CFFI_GETOP(op));
        return NULL;
    }
}


struct _cffi_type_context_s global_ctx = {
};


static PyObject *b_test(PyObject *self, PyObject *args)
{
    char *s;
    if (!PyArg_ParseTuple(args, "s", &s))
        return NULL;

    _cffi_opcode_t opcodes[100];
    struct _cffi_parse_info_s parse_info = {
        .ctx = &global_ctx,
        .output = opcodes,
        .output_size = 100,
    };
    int res = parse_c_type(&parse_info, s);
    if (res < 0) {
        PyErr_SetString(PyExc_ValueError, parse_info.error_message);
        return NULL;
    }

    return realize_c_type(&global_ctx, opcodes, res);
}

static PyMethodDef MyMethods[] = {
    {"test",   b_test,  METH_VARARGS},
    {NULL,     NULL}    /* Sentinel */
};

PyMODINIT_FUNC
initrealize_c_type(void)
{
    PyObject *m = Py_InitModule("realize_c_type", MyMethods);
    (void)m;
}
