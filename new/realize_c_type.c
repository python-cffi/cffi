
typedef struct {
    struct _cffi_type_context_s ctx;   /* inlined substructure */
    PyObject *types_dict;
} builder_c_t;


static PyObject *all_primitives[_CFFI__NUM_PRIM];
static PyObject *global_types_dict;

static PyObject *build_primitive_type(int num);   /* forward */

static int init_global_types_dict(PyObject *ffi_type_dict)
{
    int err;
    PyObject *ct, *ct2, *pnull;

    global_types_dict = PyDict_New();
    if (global_types_dict == NULL)
        return -1;

    ct = build_primitive_type(_CFFI_PRIM_VOID);         // 'void'
    if (ct == NULL)
        return -1;
    if (PyDict_SetItemString(global_types_dict,
                             ((CTypeDescrObject *)ct)->ct_name, ct) < 0) {
        return -1;
    }
    ct2 = new_pointer_type((CTypeDescrObject *)ct);     // 'void *'
    if (ct2 == NULL)
        return -1;
    if (PyDict_SetItemString(global_types_dict,
                             ((CTypeDescrObject *)ct2)->ct_name, ct2) < 0) {
        Py_DECREF(ct2);
        return -1;
    }

    pnull = new_simple_cdata(NULL, (CTypeDescrObject *)ct2);
    Py_DECREF(ct2);
    if (pnull == NULL)
        return -1;
    err = PyDict_SetItemString(ffi_type_dict, "NULL", pnull);
    Py_DECREF(pnull);
    return err;
}

static void free_builder_c(builder_c_t *builder)
{
    Py_XDECREF(builder->types_dict);

    const void *mem[] = {builder->ctx.types,
                         builder->ctx.globals,
                         builder->ctx.struct_unions,
                         builder->ctx.fields,
                         builder->ctx.enums,
                         builder->ctx.typenames};
    int i;
    for (i = 0; i < sizeof(mem) / sizeof(*mem); i++) {
        if (mem[i] != NULL)
            PyMem_Free((void *)mem[i]);
    }
    PyMem_Free(builder);
}

static builder_c_t *new_builder_c(const struct _cffi_type_context_s *ctx)
{
    PyObject *ldict = PyDict_New();
    if (ldict == NULL)
        return NULL;

    builder_c_t *builder = PyMem_Malloc(sizeof(builder_c_t));
    if (builder == NULL) {
        Py_DECREF(ldict);
        PyErr_NoMemory();
        return NULL;
    }
    builder->ctx = *ctx;
    builder->types_dict = ldict;
    return builder;
}

static PyObject *get_unique_type(builder_c_t *builder, PyObject *x)
{
    /* Replace the CTypeDescrObject 'x' with a standardized one.
       This either just returns x, or x is decrefed and a new reference
       to the standard equivalent is returned.

       In this function, 'x' always contains a reference that must be
       decrefed, and 'y' never does.
    */
    CTypeDescrObject *ct = (CTypeDescrObject *)x;
    if (ct == NULL)
        return NULL;

    /* XXX maybe change the type of ct_name to be a real 'PyObject *'? */
    PyObject *name = PyString_FromString(ct->ct_name);
    if (name == NULL)
        goto no_memory;

    PyObject *y = PyDict_GetItem(builder->types_dict, name);
    if (y != NULL) {
        /* Already found the same ct_name in the dict.  Return the old one. */
        Py_INCREF(y);
        Py_DECREF(x);
        x = y;
        goto done;
    }

    if (!(ct->ct_flags & CT_USES_LOCAL)) {
        /* The type is not "local", i.e. does not make use of any struct,
           union or enum.  This means it should be shared across independent
           ffi instances.  Look it up and possibly add it to the global
           types dict.
        */
        y = PyDict_GetItem(global_types_dict, name);
        if (y != NULL) {
            Py_INCREF(y);
            Py_DECREF(x);
            x = y;
        }
        else {
            /* Not found in the global dictionary.  Put it there. */
            if (PyDict_SetItem(global_types_dict, name, x) < 0)
                goto no_memory;
        }
    }

    /* Set x in the local dict. */
    if (PyDict_SetItem(builder->types_dict, name, x) < 0)
        goto no_memory;

 done:
    Py_DECREF(name);
    return x;

 no_memory:
    Py_XDECREF(name);
    Py_DECREF(x);
    return NULL;
}

static PyObject *build_primitive_type(int num)
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
_realize_c_type_or_func(builder_c_t *builder,
                        _cffi_opcode_t opcodes[], int index);  /* forward */


/* Interpret an opcodes[] array.  If opcodes == ctx->types, store all
   the intermediate types back in the opcodes[].  Returns a new
   reference.
*/
static CTypeDescrObject *
realize_c_type(builder_c_t *builder, _cffi_opcode_t opcodes[], int index)
{
    PyObject *x = _realize_c_type_or_func(builder, opcodes, index);
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
_realize_c_type_or_func(builder_c_t *builder,
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
        y = _realize_c_type_or_func(builder, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        if (CTypeDescr_Check(y)) {
            x = new_pointer_type((CTypeDescrObject *)y);
            x = get_unique_type(builder, x);
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
        y = (PyObject *)realize_c_type(builder, opcodes, _CFFI_GETARG(op));
        if (y == NULL)
            return NULL;
        z = new_pointer_type((CTypeDescrObject *)y);
        z = get_unique_type(builder, z);
        Py_DECREF(y);
        if (z == NULL)
            return NULL;
        x = new_array_type((CTypeDescrObject *)z, length);
        x = get_unique_type(builder, x);
        Py_DECREF(z);
        break;

    case _CFFI_OP_STRUCT_UNION:
    {
        const struct _cffi_struct_union_s *s;
        _cffi_opcode_t op2;

        s = &builder->ctx.struct_unions[_CFFI_GETARG(op)];
        op2 = builder->ctx.types[s->type_index];
        if ((((uintptr_t)op2) & 1) == 0) {
            x = (PyObject *)op2;
            Py_INCREF(x);
        }
        else {
            int flags;
            char *name = alloca(8 + strlen(s->name));
            if (s->flags & CT_UNION) {
                strcpy(name, "union ");
                flags = CT_UNION;
            }
            else {
                strcpy(name, "struct ");
                flags = CT_STRUCT;
            }
            strcat(name, s->name);
            x = new_struct_or_union_type(name, flags);

            if (s->first_field_index >= 0) {
                CTypeDescrObject *ct = (CTypeDescrObject *)x;
                ct->ct_size = s->size;
                ct->ct_length = s->alignment;
                ct->ct_flags &= ~CT_IS_OPAQUE;
                ct->ct_flags |= CT_LAZY_FIELD_LIST;
                ct->ct_extra = builder;
            }

            /* We are going to update the "primary" OP_STRUCT_OR_UNION
               slot below, which may be the same or a different one as
               the "current" slot.  If it is a different one, the
               current slot is not updated.  But in this case, the
               next time we walk the same current slot, we'll find the
               'x' object in the primary slot (op2, above) and then we
               will update the current slot. */
            opcodes = builder->ctx.types;
            index = s->type_index;
        }
        break;
    }

    case _CFFI_OP_FUNCTION:
    {
        PyObject *fargs;
        int i, base_index, num_args;

        y = (PyObject *)realize_c_type(builder, opcodes, _CFFI_GETARG(op));
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
            z = (PyObject *)realize_c_type(builder, opcodes, base_index + i);
            if (z == NULL) {
                Py_DECREF(fargs);
                Py_DECREF(y);
                return NULL;
            }
            PyTuple_SET_ITEM(fargs, i, z);
        }

        z = new_function_type(fargs, (CTypeDescrObject *)y, 0, FFI_DEFAULT_ABI);
        z = get_unique_type(builder, z);
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
        x = _realize_c_type_or_func(builder, opcodes, _CFFI_GETARG(op));
        break;

    case _CFFI_OP_TYPENAME:
    {
        /* essential: the TYPENAME opcode resolves the type index looked
           up in the 'ctx->typenames' array, but it does so in 'ctx->types'
           instead of in 'opcodes'! */
        int type_index = builder->ctx.typenames[_CFFI_GETARG(op)].type_index;
        x = _realize_c_type_or_func(builder, builder->ctx.types, type_index);
        break;
    }

    default:
        PyErr_Format(PyExc_NotImplementedError, "op=%d", (int)_CFFI_GETOP(op));
        return NULL;
    }

    if (x != NULL && opcodes == builder->ctx.types) {
        assert((((uintptr_t)x) & 1) == 0);
        assert((((uintptr_t)opcodes[index]) & 1) == 1);
        Py_INCREF(x);
        opcodes[index] = x;
    }
    return x;
};

static int do_realize_lazy_struct(CTypeDescrObject *ct)
{
    assert(ct->ct_flags & (CT_STRUCT | CT_UNION));

    if (ct->ct_flags & CT_LAZY_FIELD_LIST) {
        assert(!(ct->ct_flags & CT_IS_OPAQUE));

        builder_c_t *builder = ct->ct_extra;
        assert(builder != NULL);

        char *p = ct->ct_name;
        if (memcmp(p, "struct ", 7) == 0)
            p += 7;
        else if (memcmp(p, "union ", 6) == 0)
            p += 6;

        int n = search_in_struct_unions(&builder->ctx, p, strlen(p));
        if (n < 0)
            Py_FatalError("lost a struct/union!");

        const struct _cffi_struct_union_s *s = &builder->ctx.struct_unions[n];
        const struct _cffi_field_s *fld =
            &builder->ctx.fields[s->first_field_index];

        /* XXX painfully build all the Python objects that are the args
           to b_complete_struct_or_union() */

        PyObject *fields = PyList_New(s->num_fields);
        if (fields == NULL)
            return -1;

        int i;
        for (i = 0; i < s->num_fields; i++, fld++) {
            _cffi_opcode_t op = fld->field_type_op;
            PyObject *f;
            CTypeDescrObject *ctf;

            switch (_CFFI_GETOP(op)) {

            case _CFFI_OP_NOOP:
                ctf = realize_c_type(builder, builder->ctx.types,
                                     _CFFI_GETARG(op));
                break;

            default:
                PyErr_Format(PyExc_NotImplementedError, "field op=%d",
                             (int)_CFFI_GETOP(op));
                return -1;
            }

            if (ctf->ct_size != fld->field_size) {
                PyErr_Format(FFIError,
                             "%s field '%s' was declared in the cdef to be"
                             " %zd bytes, but is actually %zd bytes",
                             ct->ct_name, fld->name,
                             ctf->ct_size, fld->field_size);
                return -1;
            }

            f = Py_BuildValue("(sOin)", fld->name, ctf,
                              (int)-1, (Py_ssize_t)fld->field_offset);
            if (f == NULL) {
                Py_DECREF(fields);
                return -1;
            }
            PyList_SET_ITEM(fields, i, f);
        }

        PyObject *args = Py_BuildValue("(OOOnn)", ct, fields,
                                       Py_None,
                                       (Py_ssize_t)s->size,
                                       (Py_ssize_t)s->alignment);
        Py_DECREF(fields);
        if (args == NULL)
            return -1;

        ct->ct_extra = NULL;
        ct->ct_flags |= CT_IS_OPAQUE;
        PyObject *res = b_complete_struct_or_union(NULL, args);
        ct->ct_flags &= ~CT_IS_OPAQUE;
        Py_DECREF(args);
        if (res == NULL) {
            ct->ct_extra = builder;
            return -1;
        }

        assert(ct->ct_stuff != NULL);
        ct->ct_flags &= ~CT_LAZY_FIELD_LIST;
        Py_DECREF(res);
        return 1;
    }
    else {
        assert(ct->ct_flags & CT_IS_OPAQUE);
        return 0;
    }
}
