
static PyObject *all_primitives[_CFFI__NUM_PRIM];


PyObject *build_primitive_type(int num)
{
    /* XXX too many translations between here and new_primitive_type() */
    static const char *primitive_name[] = {
        NULL,
        "_Bool",
        "char",
        "signed char",
        "unsigned char",
        "short",
        "unsigned short",
        "int",
        "unsigned int",
        "long",
        "unsigned long",
        "long long",
        "unsigned long long",
        "float",
        "double",
        "long double",
        "wchar_t",
        "int8_t",
        "uint8_t",
        "int16_t",
        "uint16_t",
        "int32_t",
        "uint32_t",
        "int64_t",
        "uint64_t",
        "intptr_t",
        "uintptr_t",
        "ptrdiff_t",
        "size_t",
        "ssize_t",
    };
    PyObject *x;

    if (num == _CFFI_PRIM_VOID) {
        x = new_void_type();
    }
    else if (0 <= num &&
             num < sizeof(primitive_name) / sizeof(*primitive_name) &&
             primitive_name[num] != NULL) {
        x = new_primitive_type(primitive_name[num]);
    }
    else {
        PyErr_Format(PyExc_NotImplementedError, "prim=%d", num);
        return NULL;
    }

    all_primitives[num] = x;
    return x;
}


static PyObject *
_realize_c_type_or_func(const struct _cffi_type_context_s *ctx,
                        _cffi_opcode_t opcodes[], int index);  /* forward */


/* Interpret an opcodes[] array.  If opcodes == ctx->types, store all
   the intermediate types back in the opcodes[].  Returns a new
   reference.
*/
static CTypeDescrObject *
realize_c_type(const struct _cffi_type_context_s *ctx,
               _cffi_opcode_t opcodes[], int index)
{
    PyObject *x = _realize_c_type_or_func(ctx, opcodes, index);
    if (x == NULL || CTypeDescr_Check(x)) {
        return (CTypeDescrObject *)x;
    }
    else {
        PyObject *y;
        assert(PyTuple_Check(x));
        y = PyTuple_GET_ITEM(x, 0);
        char *text1 = ((CTypeDescrObject *)y)->ct_name;
        char *text2 = text1 + ((CTypeDescrObject *)y)->ct_name_position + 1;
        assert(text2[-3] == '(');
        text2[-3] = '\0';
        PyErr_Format(FFIError, "the type '%s%s' is a function type, not a "
                               "pointer-to-function type", text1, text2);
        text2[-3] = '(';
        Py_DECREF(x);
        return NULL;
    }
}

static PyObject *
_realize_c_type_or_func(const struct _cffi_type_context_s *ctx,
                        _cffi_opcode_t opcodes[], int index)
{
    PyObject *x, *y, *z;
    _cffi_opcode_t op = opcodes[index];
    Py_ssize_t length = -1;

    if ((((uintptr_t)op) & 1) == 0) {
        x = (PyObject *)op;
        Py_INCREF(x);
        return x;
    }

    switch (_CFFI_GETOP(op)) {

    case _CFFI_OP_PRIMITIVE:
        x = all_primitives[_CFFI_GETARG(op)];
        if (x == NULL)
            x = build_primitive_type(_CFFI_GETARG(op));
        Py_XINCREF(x);
        break;

    case _CFFI_OP_POINTER:
        y = _realize_c_type_or_func(ctx, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        if (CTypeDescr_Check(y)) {
            x = new_pointer_type((CTypeDescrObject *)y);
        }
        else {
            assert(PyTuple_Check(y));   /* from _CFFI_OP_FUNCTION */
            x = PyTuple_GET_ITEM(y, 0);
            Py_INCREF(x);
        }
        Py_DECREF(y);
        break;

    case _CFFI_OP_ARRAY:
        length = (Py_ssize_t)opcodes[index + 1];
        /* fall-through */
    case _CFFI_OP_OPEN_ARRAY:
        y = (PyObject *)realize_c_type(ctx, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        z = new_pointer_type((CTypeDescrObject *)y);
        Py_DECREF(y);
        if (z == NULL)
            return NULL;
        x = new_array_type((CTypeDescrObject *)z, length);
        Py_DECREF(z);
        break;

    case _CFFI_OP_STRUCT_UNION:
    {
        const struct _cffi_struct_union_s *s;
        _cffi_opcode_t op2;

        s = &ctx->struct_unions[_CFFI_GETARG(op)];
        op2 = ctx->types[s->type_index];
        if ((((uintptr_t)op2) & 1) == 0) {
            x = (PyObject *)op2;
            Py_INCREF(x);
        }
        else {
            x = new_struct_or_union_type(s->name, CT_STRUCT);
            /* We are going to update the "primary" OP_STRUCT_OR_UNION
               slot below, which may be the same or a different one as
               the "current" slot.  If it is a different one, the
               current slot is not updated.  But in this case, the
               next time we walk the same current slot, we'll find the
               'x' object in the primary slot (op2, above) and then we
               will update the current slot. */
            opcodes = ctx->types;
            index = s->type_index;
        }
        break;
    }

    case _CFFI_OP_FUNCTION:
    {
        PyObject *fargs;
        int i, base_index, num_args;

        y = (PyObject *)realize_c_type(ctx, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;

        base_index = index + 1;
        num_args = 0;
        while (_CFFI_GETOP(opcodes[base_index + num_args]) !=
                   _CFFI_OP_FUNCTION_END)
            num_args++;

        fargs = PyTuple_New(num_args);
        if (fargs == NULL) {
            Py_DECREF(y);
            return NULL;
        }

        for (i = 0; i < num_args; i++) {
            z = (PyObject *)realize_c_type(ctx, opcodes, base_index + i);
            if (z == NULL) {
                Py_DECREF(fargs);
                Py_DECREF(y);
                return NULL;
            }
            PyTuple_SET_ITEM(fargs, i, z);
        }

        z = new_function_type(fargs, (CTypeDescrObject *)y, 0, FFI_DEFAULT_ABI);
        Py_DECREF(fargs);
        Py_DECREF(y);
        if (z == NULL)
            return NULL;

        x = PyTuple_Pack(1, z);   /* hack: hide the CT_FUNCTIONPTR.  it will
                                     be revealed again by the OP_POINTER */
        Py_DECREF(z);
        break;
    }

    case _CFFI_OP_NOOP:
        x = _realize_c_type_or_func(ctx, opcodes, _CFFI_GETARG(op));
        break;

    case _CFFI_OP_TYPENAME:
    {
        /* essential: the TYPENAME opcode resolves the type index looked
           up in the 'ctx->typenames' array, but it does so in 'ctx->types'
           instead of in 'opcodes'! */
        int type_index = ctx->typenames[_CFFI_GETARG(op)].type_index;
        x = _realize_c_type_or_func(ctx, ctx->types, type_index);
        break;
    }

    default:
        PyErr_Format(PyExc_NotImplementedError, "op=%d", (int)_CFFI_GETOP(op));
        return NULL;
    }

    if (x != NULL && opcodes == ctx->types) {
        assert((((uintptr_t)x) & 1) == 0);
        assert((((uintptr_t)opcodes[index]) & 1) == 1);
        Py_INCREF(x);
        opcodes[index] = x;
    }
    return x;
};
