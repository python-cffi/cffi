
static CTypeDescrObject *all_primitives[_CFFI__NUM_PRIM];


CTypeDescrObject *build_primitive_type(int num)
{
    CTypeDescrObject *x;

    switch (num) {

    case _CFFI_PRIM_VOID:
        x = new_void_type();
        break;

    case _CFFI_PRIM_INT:
        x = new_primitive_type("int");
        break;

    default:
        PyErr_Format(PyExc_NotImplementedError, "prim=%d", num);
        return NULL;
    }

    all_primitives[num] = x;
    return x;
}


/* Interpret an opcodes[] array.  If opcodes == ctx->types, store all
   the intermediate types back in the opcodes[].  Returns a new
   reference.
*/
CTypeDescrObject *realize_c_type(const struct _cffi_type_context_s *ctx,
                                 _cffi_opcode_t opcodes[], int index)
{
    CTypeDescrObject *ct;
    CTypeDescrObject *x, *y, *z;
    _cffi_opcode_t op = opcodes[index];
    Py_ssize_t length = -1;

    if ((((uintptr_t)op) & 1) == 0) {
        ct = (CTypeDescrObject *)op;
        Py_INCREF(ct);
        return ct;
    }

    switch (_CFFI_GETOP(op)) {

    case _CFFI_OP_PRIMITIVE:
        x = all_primitives[_CFFI_GETARG(op)];
        if (x == NULL)
            x = build_primitive_type(_CFFI_GETARG(op));
        Py_XINCREF(x);
        break;

    case _CFFI_OP_POINTER:
        y = realize_c_type(ctx, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        x = new_pointer_type(y);
        Py_DECREF(y);
        break;

    case _CFFI_OP_ARRAY:
        length = (Py_ssize_t)opcodes[_CFFI_GETARG(op) + 1];
        /* fall-through */
    case _CFFI_OP_OPEN_ARRAY:
        y = realize_c_type(ctx, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        z = new_pointer_type(y);
        Py_DECREF(y);
        if (z == NULL)
            return NULL;
        x = new_array_type(z, length);
        Py_DECREF(z);
        break;

    case _CFFI_OP_NOOP:
        x = realize_c_type(ctx, opcodes, _CFFI_GETARG(op));
        break;

    default:
        PyErr_Format(PyExc_NotImplementedError, "op=%d", (int)_CFFI_GETOP(op));
        return NULL;
    }

    if (x != NULL && opcodes == ctx->types) {
        assert((((uintptr_t)x) & 1) == 0);
        Py_INCREF(x);
        opcodes[index] = x;
    }
    return x;
};
