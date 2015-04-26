
/* An FFI object has methods like ffi.new().  It is also a container
   for the type declarations (typedefs and structs) that you can use,
   say in ffi.new().

   CTypeDescrObjects are internally stored in the dict 'types_dict'.
   The types_dict is lazily filled with CTypeDescrObjects made from
   reading a _cffi_type_context_s structure.

   In "modern" mode, the FFI instance is made by the C extension
   module originally created by recompile().  The _cffi_type_context_s
   structure comes from global data in the C extension module.

   In "compatibility" mode, an FFI instance is created explicitly by
   the user, and its _cffi_type_context_s is initially empty.  You
   need to call ffi.cdef() to add more information to it.
*/

#define FFI_COMPLEXITY_OUTPUT   1200     /* xxx should grow as needed */

struct FFIObject_s {
    PyObject_HEAD
    PyObject *gc_wrefs;
    struct _cffi_parse_info_s info;
    int ctx_is_static;
    builder_c_t *types_builder;
    PyObject *dynamic_types;
    _cffi_opcode_t internal_output[FFI_COMPLEXITY_OUTPUT];
};

static FFIObject *ffi_internal_new(PyTypeObject *ffitype,
                                 const struct _cffi_type_context_s *static_ctx)
{
    FFIObject *ffi;
    if (static_ctx != NULL) {
        ffi = (FFIObject *)PyObject_GC_New(FFIObject, ffitype);
        /* we don't call PyObject_GC_Track() here: from _cffi_init_module()
           it is not needed, because in this case the ffi object is immortal */
    }
    else {
        ffi = (FFIObject *)ffitype->tp_alloc(ffitype, 0);
    }
    if (ffi == NULL)
        return NULL;

    ffi->types_builder = new_builder_c(static_ctx);
    if (ffi->types_builder == NULL) {
        Py_DECREF(ffi);
        return NULL;
    }
    ffi->gc_wrefs = NULL;
    ffi->info.ctx = &ffi->types_builder->ctx;
    ffi->info.output = ffi->internal_output;
    ffi->info.output_size = FFI_COMPLEXITY_OUTPUT;
    ffi->ctx_is_static = (static_ctx != NULL);
    ffi->dynamic_types = NULL;
    return ffi;
}

static void ffi_dealloc(FFIObject *ffi)
{
    PyObject_GC_UnTrack(ffi);
    Py_XDECREF(ffi->gc_wrefs);
    Py_XDECREF(ffi->dynamic_types);

    if (!ffi->ctx_is_static)
        free_builder_c(ffi->types_builder);

    Py_TYPE(ffi)->tp_free((PyObject *)ffi);
}

static int ffi_traverse(FFIObject *ffi, visitproc visit, void *arg)
{
    Py_VISIT(ffi->types_builder->types_dict);
    Py_VISIT(ffi->gc_wrefs);
    return 0;
}

static PyObject *ffiobj_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    /* user-facing initialization code, for explicit FFI() calls */
    return (PyObject *)ffi_internal_new(type, NULL);
}

static int ffiobj_init(PyObject *self, PyObject *args, PyObject *kwds)
{
    char *keywords[] = {NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, ":FFI", keywords))
        return -1;
    return 0;
}

#define ACCEPT_STRING   1
#define ACCEPT_CTYPE    2
#define ACCEPT_CDATA    4
#define ACCEPT_ALL      (ACCEPT_STRING | ACCEPT_CTYPE | ACCEPT_CDATA)
#define CONSIDER_FN_AS_FNPTR  8

static CTypeDescrObject *_ffi_type(FFIObject *ffi, PyObject *arg,
                                   int accept)
{
    /* Returns the CTypeDescrObject from the user-supplied 'arg'.
       Does not return a new reference!
    */
    if ((accept & ACCEPT_STRING) && PyText_Check(arg)) {
        PyObject *types_dict = ffi->types_builder->types_dict;
        PyObject *x = PyDict_GetItem(types_dict, arg);
        if (x != NULL) {
            assert(CTypeDescr_Check(x));
            return (CTypeDescrObject *)x;
        }

        char *input_text = PyText_AS_UTF8(arg);
        int index = parse_c_type(&ffi->info, input_text);
        if (index < 0) {
            size_t num_spaces = ffi->info.error_location;
            char spaces[num_spaces + 1];
            memset(spaces, ' ', num_spaces);
            spaces[num_spaces] = '\0';
            PyErr_Format(FFIError, "%s\n%s\n%s^", ffi->info.error_message,
                         input_text, spaces);
            return NULL;
        }
        CTypeDescrObject *ct;
        if (accept & CONSIDER_FN_AS_FNPTR) {
            ct = realize_c_type_fn_as_fnptr(ffi->types_builder,
                                            ffi->info.output, index);
        }
        else {
            ct = realize_c_type(ffi->types_builder, ffi->info.output, index);
        }
        if (ct == NULL)
            return NULL;

        /* Cache under the name given by 'arg', in addition to the
           fact that the same ct is probably already cached under
           its standardized name.  In a few cases, it is not, e.g.
           if it is a primitive; for the purpose of this function,
           the important point is the following line, which makes
           sure that in any case the next _ffi_type() with the same
           'arg' will succeed early, in PyDict_GetItem() above.
        */
        int err = PyDict_SetItem(types_dict, arg, (PyObject *)ct);
        Py_DECREF(ct);   /* we know it was written in types_dict (unless we got
                     out of memory), so there is at least this reference left */
        if (err < 0)
            return NULL;
        return ct;
    }
    else if ((accept & ACCEPT_CTYPE) && CTypeDescr_Check(arg)) {
        return (CTypeDescrObject *)arg;
    }
    else if ((accept & ACCEPT_CDATA) && CData_Check(arg)) {
        return ((CDataObject *)arg)->c_type;
    }
    else {
        const char *m1 = (accept & ACCEPT_STRING) ? "string" : "";
        const char *m2 = (accept & ACCEPT_CTYPE) ? "ctype object" : "";
        const char *m3 = (accept & ACCEPT_CDATA) ? "cdata object" : "";
        const char *s12 = (*m1 && (*m2 || *m3)) ? " or " : "";
        const char *s23 = (*m2 && *m3) ? " or " : "";
        PyErr_Format(PyExc_TypeError, "expected a %s%s%s%s%s, got '%.200s'",
                     m1, s12, m2, s23, m3,
                     Py_TYPE(arg)->tp_name);
        return NULL;
    }
}

PyDoc_STRVAR(ffi_sizeof_doc,
"Return the size in bytes of the argument.\n"
"It can be a string naming a C type, or a 'cdata' instance.");

static PyObject *ffi_sizeof(FFIObject *self, PyObject *arg)
{
    Py_ssize_t size;
    CTypeDescrObject *ct = _ffi_type(self, arg, ACCEPT_ALL);
    if (ct == NULL)
        return NULL;

    size = ct->ct_size;

    if (CData_Check(arg)) {
        CDataObject *cd = (CDataObject *)arg;
        if (cd->c_type->ct_flags & CT_ARRAY)
            size = get_array_length(cd) * cd->c_type->ct_itemdescr->ct_size;
    }

    if (size < 0) {
        PyErr_Format(FFIError, "don't know the size of ctype '%s'",
                     ct->ct_name);
        return NULL;
    }
    return PyInt_FromSsize_t(size);
}

PyDoc_STRVAR(ffi_alignof_doc,
"Return the natural alignment size in bytes of the argument.\n"
"It can be a string naming a C type, or a 'cdata' instance.");

static PyObject *ffi_alignof(FFIObject *self, PyObject *arg)
{
    int align;
    CTypeDescrObject *ct = _ffi_type(self, arg, ACCEPT_ALL);
    if (ct == NULL)
        return NULL;

    align = get_alignment(ct);
    if (align < 0)
        return NULL;
    return PyInt_FromLong(align);
}

PyDoc_STRVAR(ffi_typeof_doc,
"Parse the C type given as a string and return the\n"
"corresponding <ctype> object.\n"
"It can also be used on 'cdata' instance to get its C type.");

static PyObject *_cpyextfunc_type_index(PyObject *x);  /* forward */

static PyObject *ffi_typeof(FFIObject *self, PyObject *arg)
{
    PyObject *x = (PyObject *)_ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CDATA);
    if (x != NULL) {
        Py_INCREF(x);
    }
    else {
        x = _cpyextfunc_type_index(arg);
    }
    return x;
}

PyDoc_STRVAR(ffi_new_doc,
"Allocate an instance according to the specified C type and return a\n"
"pointer to it.  The specified C type must be either a pointer or an\n"
"array: ``new('X *')`` allocates an X and returns a pointer to it,\n"
"whereas ``new('X[n]')`` allocates an array of n X'es and returns an\n"
"array referencing it (which works mostly like a pointer, like in C).\n"
"You can also use ``new('X[]', n)`` to allocate an array of a\n"
"non-constant length n.\n"
"\n"
"The memory is initialized following the rules of declaring a global\n"
"variable in C: by default it is zero-initialized, but an explicit\n"
"initializer can be given which can be used to fill all or part of the\n"
"memory.\n"
"\n"
"When the returned <cdata> object goes out of scope, the memory is\n"
"freed.  In other words the returned <cdata> object has ownership of\n"
"the value of type 'cdecl' that it points to.  This means that the raw\n"
"data can be used as long as this object is kept alive, but must not be\n"
"used for a longer time.  Be careful about that when copying the\n"
"pointer to the memory somewhere else, e.g. into another structure.");

static PyObject *ffi_new(FFIObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    PyObject *arg, *init = Py_None;
    if (!PyArg_ParseTuple(args, "O|O:new", &arg, &init))
        return NULL;

    ct = _ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CTYPE);
    if (ct == NULL)
        return NULL;

    return direct_newp(ct, init);
}

PyDoc_STRVAR(ffi_cast_doc,
"Similar to a C cast: returns an instance of the named C\n"
"type initialized with the given 'source'.  The source is\n"
"casted between integers or pointers of any type.");

static PyObject *ffi_cast(FFIObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    PyObject *ob, *arg;
    if (!PyArg_ParseTuple(args, "OO:cast", &arg, &ob))
        return NULL;

    ct = _ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CTYPE);
    if (ct == NULL)
        return NULL;

    return do_cast(ct, ob);
}

PyDoc_STRVAR(ffi_string_doc,
"Return a Python string (or unicode string) from the 'cdata'.  If\n"
"'cdata' is a pointer or array of characters or bytes, returns the\n"
"null-terminated string.  The returned string extends until the first\n"
"null character, or at most 'maxlen' characters.  If 'cdata' is an\n"
"array then 'maxlen' defaults to its length.\n"
"\n"
"If 'cdata' is a pointer or array of wchar_t, returns a unicode string\n"
"following the same rules.\n"
"\n"
"If 'cdata' is a single character or byte or a wchar_t, returns it as a\n"
"string or unicode string.\n"
"\n"
"If 'cdata' is an enum, returns the value of the enumerator as a\n"
"string, or 'NUMBER' if the value is out of range.");

#define ffi_string  b_string     /* ffi_string() => b_string()
                                    from _cffi_backend.c */

PyDoc_STRVAR(ffi_offsetof_doc,
"Return the offset of the named field inside the given structure or\n"
"array, which must be given as a C type name.  You can give several\n"
"field names in case of nested structures.  You can also give numeric\n"
"values which correspond to array items, in case of an array type.");

static PyObject *ffi_offsetof(FFIObject *self, PyObject *args)
{
    PyObject *arg;
    CTypeDescrObject *ct;
    Py_ssize_t i, offset;

    if (PyTuple_Size(args) < 2) {
        PyErr_SetString(PyExc_TypeError,
                        "offsetof() expects at least 2 arguments");
        return NULL;
    }

    arg = PyTuple_GET_ITEM(args, 0);
    ct = _ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CTYPE);
    if (ct == NULL)
        return NULL;

    offset = 0;
    for (i = 1; i < PyTuple_GET_SIZE(args); i++) {
        Py_ssize_t ofs1;
        ct = direct_typeoffsetof(ct, PyTuple_GET_ITEM(args, i), i > 1, &ofs1);
        if (ct == NULL)
            return NULL;
        offset += ofs1;
    }
    return PyInt_FromSsize_t(offset);
}

PyDoc_STRVAR(ffi_addressof_doc,
"With a single arg, return the address of a <cdata 'struct-or-union'>.\n"
"If 'fields_or_indexes' are given, returns the address of that field or\n"
"array item in the structure or array, recursively in case of nested\n"
"structures.");

static PyObject *ffi_addressof(FFIObject *self, PyObject *args)
{
    PyObject *arg, *z, *result;
    CTypeDescrObject *ct;
    Py_ssize_t i, offset = 0;
    int accepted_flags;

    if (PyTuple_Size(args) < 1) {
        PyErr_SetString(PyExc_TypeError,
                        "addressof() expects at least 1 argument");
        return NULL;
    }

    arg = PyTuple_GET_ITEM(args, 0);
    ct = _ffi_type(self, arg, ACCEPT_CDATA);
    if (ct == NULL)
        return NULL;

    if (PyTuple_GET_SIZE(args) == 1) {
        accepted_flags = CT_STRUCT | CT_UNION | CT_ARRAY;
        if ((ct->ct_flags & accepted_flags) == 0) {
            PyErr_SetString(PyExc_TypeError,
                            "expected a cdata struct/union/array object");
            return NULL;
        }
    }
    else {
        accepted_flags = CT_STRUCT | CT_UNION | CT_ARRAY | CT_POINTER;
        if ((ct->ct_flags & accepted_flags) == 0) {
            PyErr_SetString(PyExc_TypeError,
                        "expected a cdata struct/union/array/pointer object");
            return NULL;
        }
        for (i = 1; i < PyTuple_GET_SIZE(args); i++) {
            Py_ssize_t ofs1;
            ct = direct_typeoffsetof(ct, PyTuple_GET_ITEM(args, i),
                                     i > 1, &ofs1);
            if (ct == NULL)
                return NULL;
            offset += ofs1;
        }
    }

    z = new_pointer_type(ct);
    z = get_unique_type(self->types_builder, z);
    if (z == NULL)
        return NULL;

    result = new_simple_cdata(((CDataObject *)arg)->c_data + offset,
                              (CTypeDescrObject *)z);
    Py_DECREF(z);
    return result;
}

static PyObject *_combine_type_name_l(CTypeDescrObject *ct,
                                      size_t extra_text_len)
{
    size_t base_name_len;
    PyObject *result;
    char *p;

    base_name_len = strlen(ct->ct_name);
    result = PyString_FromStringAndSize(NULL, base_name_len + extra_text_len);
    if (result == NULL)
        return NULL;

    p = PyString_AS_STRING(result);
    memcpy(p, ct->ct_name, ct->ct_name_position);
    p += ct->ct_name_position;
    p += extra_text_len;
    memcpy(p, ct->ct_name + ct->ct_name_position,
           base_name_len - ct->ct_name_position);
    return result;
}

PyDoc_STRVAR(ffi_getctype_doc,
"Return a string giving the C type 'cdecl', which may be itself a\n"
"string or a <ctype> object.  If 'replace_with' is given, it gives\n"
"extra text to append (or insert for more complicated C types), like a\n"
"variable name, or '*' to get actually the C type 'pointer-to-cdecl'.");

static PyObject *ffi_getctype(FFIObject *self, PyObject *args)
{
    PyObject *cdecl, *res;
    char *p, *replace_with = "";
    int add_paren, add_space;
    CTypeDescrObject *ct;
    size_t replace_with_len;

    if (!PyArg_ParseTuple(args, "O|s:getctype", &cdecl, &replace_with))
        return NULL;

    ct = _ffi_type(self, cdecl, ACCEPT_STRING|ACCEPT_CTYPE);
    if (ct == NULL)
        return NULL;

    while (replace_with[0] != 0 && isspace(replace_with[0]))
        replace_with++;
    replace_with_len = strlen(replace_with);
    while (replace_with_len > 0 && isspace(replace_with[replace_with_len - 1]))
        replace_with_len--;

    add_paren = (replace_with[0] == '*' &&
                 ((ct->ct_flags & CT_ARRAY) != 0));
    add_space = (!add_paren && replace_with_len > 0 &&
                 replace_with[0] != '[' && replace_with[0] != '(');

    res = _combine_type_name_l(ct, replace_with_len + add_space + 2*add_paren);
    if (res == NULL)
        return NULL;

    p = PyString_AS_STRING(res) + ct->ct_name_position;
    if (add_paren)
        *p++ = '(';
    if (add_space)
        *p++ = ' ';
    memcpy(p, replace_with, replace_with_len);
    if (add_paren)
        p[replace_with_len] = ')';
    return res;
}

PyDoc_STRVAR(ffi_new_handle_doc,
"Return a non-NULL cdata of type 'void *' that contains an opaque\n"
"reference to the argument, which can be any Python object.  To cast it\n"
"back to the original object, use from_handle().  You must keep alive\n"
"the cdata object returned by new_handle()!");

static PyObject *ffi_new_handle(FFIObject *self, PyObject *arg)
{
    CDataObject *cd;

    cd = (CDataObject *)PyObject_GC_New(CDataObject, &CDataOwningGC_Type);
    if (cd == NULL)
        return NULL;
    Py_INCREF(g_ct_voidp);     // <ctype 'void *'>
    cd->c_type = g_ct_voidp;
    Py_INCREF(arg);
    cd->c_data = ((char *)arg) - 42;
    cd->c_weakreflist = NULL;
    PyObject_GC_Track(cd);
    return (PyObject *)cd;
}

PyDoc_STRVAR(ffi_from_handle_doc,
"Cast a 'void *' back to a Python object.  Must be used *only* on the\n"
"pointers returned by new_handle(), and *only* as long as the exact\n"
"cdata object returned by new_handle() is still alive (somewhere else\n"
"in the program).  Failure to follow these rules will crash.");

static PyObject *ffi_from_handle(PyObject *self, PyObject *arg)
{
    CTypeDescrObject *ct;
    char *raw;
    PyObject *x;
    if (!CData_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected a 'cdata' object");
        return NULL;
    }
    ct = ((CDataObject *)arg)->c_type;
    raw = ((CDataObject *)arg)->c_data;
    if (!(ct->ct_flags & CT_CAST_ANYTHING)) {
        PyErr_Format(PyExc_TypeError,
                     "expected a 'cdata' object with a 'void *' out of "
                     "new_handle(), got '%s'", ct->ct_name);
        return NULL;
    }
    if (!raw) {
        PyErr_SetString(PyExc_RuntimeError,
                        "cannot use from_handle() on NULL pointer");
        return NULL;
    }
    x = (PyObject *)(raw + 42);
    Py_INCREF(x);
    return x;
}

#if 0
static PyObject *ffi_gc(ZefFFIObject *self, PyObject *args)
{
    CDataObject *cd;
    PyObject *destructor;

    if (!PyArg_ParseTuple(args, "O!O:gc", &CData_Type, &cd, &destructor))
        return NULL;

    return gc_weakrefs_build(self, cd, destructor);
}
#endif

PyDoc_STRVAR(ffi_callback_doc,
"Return a callback object or a decorator making such a callback object.\n"
"'cdecl' must name a C function pointer type.  The callback invokes the\n"
"specified 'python_callable' (which may be provided either directly or\n"
"via a decorator).  Important: the callback object must be manually\n"
"kept alive for as long as the callback may be invoked from the C code.");

static PyObject *_ffi_callback_decorator(PyObject *outer_args, PyObject *fn)
{
    PyObject *res, *old;

    old = PyTuple_GET_ITEM(outer_args, 1);
    PyTuple_SET_ITEM(outer_args, 1, fn);
    res = b_callback(NULL, outer_args);
    PyTuple_SET_ITEM(outer_args, 1, old);
    return res;
}

static PyObject *ffi_callback(FFIObject *self, PyObject *args, PyObject *kwds)
{
    PyObject *cdecl, *python_callable = Py_None, *error = Py_None;
    PyObject *res;
    static char *keywords[] = {"cdecl", "python_callable", "error", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|OO", keywords,
                                     &cdecl, &python_callable, &error))
        return NULL;

    cdecl = (PyObject *)_ffi_type(self, cdecl, ACCEPT_STRING | ACCEPT_CTYPE |
                                               CONSIDER_FN_AS_FNPTR);
    if (cdecl == NULL)
        return NULL;

    args = Py_BuildValue("(OOO)", cdecl, python_callable, error);
    if (args == NULL)
        return NULL;

    if (python_callable != Py_None) {
        res = b_callback(NULL, args);
    }
    else {
        static PyMethodDef md = {"callback_decorator",
                                 (PyCFunction)_ffi_callback_decorator, METH_O};
        res = PyCFunction_New(&md, args);
    }
    Py_DECREF(args);
    return res;
}

PyDoc_STRVAR(ffi_errno_doc, "the value of 'errno' from/to the C calls");

static PyObject *ffi_get_errno(PyObject *self, void *closure)
{
    /* xxx maybe think about how to make the saved errno local
       to an ffi instance */
    return b_get_errno(NULL, NULL);
}

static int ffi_set_errno(PyObject *self, PyObject *newval, void *closure)
{
    PyObject *x = b_set_errno(NULL, newval);
    if (x == NULL)
        return -1;
    Py_DECREF(x);
    return 0;
}

static PyObject *ffi__set_types(FFIObject *self, PyObject *args)
{
    PyObject *lst1, *lst2;
    _cffi_opcode_t *types = NULL;
    struct _cffi_struct_union_s *struct_unions = NULL;
    struct _cffi_typename_s *typenames = NULL;

    if (!PyArg_ParseTuple(args, "O!O!",
                          &PyList_Type, &lst1, &PyList_Type, &lst2))
        return NULL;

    if (self->ctx_is_static) {
     bad_usage:
        PyMem_Free(typenames);
        PyMem_Free(struct_unions);
        PyMem_Free(types);
        if (!PyErr_Occurred())
            PyErr_SetString(PyExc_RuntimeError, "internal error");
        return NULL;
    }

    cleanup_builder_c(self->types_builder);

    int i;
    int lst1_length = PyList_GET_SIZE(lst1) / 2;
    int lst2_length = PyList_GET_SIZE(lst2) / 2;
    Py_ssize_t newsize0 = sizeof(_cffi_opcode_t) * (lst1_length + lst2_length);
    Py_ssize_t newsize1 = sizeof(struct _cffi_struct_union_s) * lst1_length;
    Py_ssize_t newsize2 = sizeof(struct _cffi_typename_s) * lst2_length;
    types = PyMem_Malloc(newsize0);
    struct_unions = PyMem_Malloc(newsize1);
    typenames = PyMem_Malloc(newsize2);
    if (!types || !struct_unions || !typenames) {
        PyErr_NoMemory();
        goto bad_usage;
    }
    memset(types, 0, newsize0);
    memset(struct_unions, 0, newsize1);
    memset(typenames, 0, newsize2);

    for (i = 0; i < lst1_length; i++) {
        PyObject *x = PyList_GET_ITEM(lst1, i * 2);
        if (!PyString_Check(x))
            goto bad_usage;
        struct_unions[i].name = PyString_AS_STRING(x);
        struct_unions[i].type_index = i;

        x = PyList_GET_ITEM(lst1, i * 2 + 1);
        if (!CTypeDescr_Check(x))
            goto bad_usage;
        types[i] = x;
        struct_unions[i].flags = ((CTypeDescrObject *)x)->ct_flags & CT_UNION;
        struct_unions[i].size = (size_t)-2;
        struct_unions[i].alignment = -2;
    }
    for (i = 0; i < lst2_length; i++) {
        PyObject *x = PyList_GET_ITEM(lst2, i * 2);
        if (!PyString_Check(x))
            goto bad_usage;
        typenames[i].name = PyString_AS_STRING(x);
        typenames[i].type_index = lst1_length + i;

        x = PyList_GET_ITEM(lst2, i * 2 + 1);
        if (!CTypeDescr_Check(x))
            goto bad_usage;
        types[lst1_length + i] = x;
    }
    for (i = 0; i < lst1_length + lst2_length; i++) {
        PyObject *x = (PyObject *)types[i];
        Py_INCREF(x);
    }

    Py_INCREF(args);     /* to keep alive the strings in '.name' */
    Py_XDECREF(self->dynamic_types);
    self->dynamic_types = args;
    self->types_builder->ctx.types = types;
    self->types_builder->num_types_imported = lst1_length + lst2_length;
    self->types_builder->ctx.struct_unions = struct_unions;
    self->types_builder->ctx.num_struct_unions = lst1_length;
    self->types_builder->ctx.typenames = typenames;
    self->types_builder->ctx.num_typenames = lst2_length;

    Py_INCREF(Py_None);
    return Py_None;
}

static PyMethodDef ffi_methods[] = {
 {"__set_types",(PyCFunction)ffi__set_types, METH_VARARGS},
 {"addressof",  (PyCFunction)ffi_addressof,  METH_VARARGS, ffi_addressof_doc},
 {"alignof",    (PyCFunction)ffi_alignof,    METH_O,       ffi_alignof_doc},
#if 0
 {"buffer",     (PyCFunction)ffi_buffer,     METH_VARARGS, ffi_buffer_doc},
#endif
 {"callback",   (PyCFunction)ffi_callback,   METH_VARARGS |
                                             METH_KEYWORDS,ffi_callback_doc},
 {"cast",       (PyCFunction)ffi_cast,       METH_VARARGS, ffi_cast_doc},
#if 0
 {"from_buffer",(PyCFunction)ffi_from_buffer,METH_O,       ffi_from_buffer_doc},
#endif
 {"from_handle",(PyCFunction)ffi_from_handle,METH_O,       ffi_from_handle_doc},
#if 0
 {"gc",         (PyCFunction)ffi_gc,         METH_VARARGS},
#endif
 {"getctype",   (PyCFunction)ffi_getctype,   METH_VARARGS, ffi_getctype_doc},
#if 0
 {"getwinerror",(PyCFunction)ffi_getwinerror,METH_VARARGS, ffi_getwinerror_doc},
#endif
 {"offsetof",   (PyCFunction)ffi_offsetof,   METH_VARARGS, ffi_offsetof_doc},
 {"new",        (PyCFunction)ffi_new,        METH_VARARGS, ffi_new_doc},
 {"new_handle", (PyCFunction)ffi_new_handle, METH_O,       ffi_new_handle_doc},
 {"sizeof",     (PyCFunction)ffi_sizeof,     METH_O,       ffi_sizeof_doc},
 {"string",     (PyCFunction)ffi_string,     METH_VARARGS, ffi_string_doc},
 {"typeof",     (PyCFunction)ffi_typeof,     METH_O,       ffi_typeof_doc},
 {NULL}
};

static PyGetSetDef ffi_getsets[] = {
    {"errno",  ffi_get_errno,  ffi_set_errno,  ffi_errno_doc},
    {NULL}
};

static PyTypeObject FFI_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "FFI",
    sizeof(FFIObject),
    0,
    (destructor)ffi_dealloc,                    /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    0,                                          /* tp_repr */
    0,                                          /* tp_as_number */
    0,                                          /* tp_as_sequence */
    0,                                          /* tp_as_mapping */
    0,                                          /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    PyObject_GenericGetAttr,                    /* tp_getattro */
    0,                                          /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC |
        Py_TPFLAGS_BASETYPE,                    /* tp_flags */
    0,                                          /* tp_doc */
    (traverseproc)ffi_traverse,                 /* tp_traverse */
    0,                                          /* tp_clear */
    0,                                          /* tp_richcompare */
    0,                                          /* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    ffi_methods,                                /* tp_methods */
    0,                                          /* tp_members */
    ffi_getsets,                                /* tp_getset */
    0,                                          /* tp_base */
    0,                                          /* tp_dict */
    0,                                          /* tp_descr_get */
    0,                                          /* tp_descr_set */
    0,                                          /* tp_dictoffset */
    ffiobj_init,                                /* tp_init */
    0,                                          /* tp_alloc */
    ffiobj_new,                                 /* tp_new */
    PyObject_GC_Del,                            /* tp_free */
};
