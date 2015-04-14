
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
    PyObject *types_dict;
    PyObject *gc_wrefs;
    struct _cffi_parse_info_s info;
    _cffi_opcode_t internal_output[FFI_COMPLEXITY_OUTPUT];
};

static FFIObject *ffi_internal_new(const struct _cffi_type_context_s *ctx)
{
    PyObject *dict = PyDict_New();
    if (dict == NULL)
        return NULL;

    FFIObject *ffi = PyObject_GC_New(FFIObject, &FFI_Type);
    if (ffi == NULL) {
        Py_DECREF(dict);
        return NULL;
    }
    ffi->types_dict = dict;
    ffi->gc_wrefs = NULL;
    ffi->info.ctx = ctx;
    ffi->info.output = ffi->internal_output;
    ffi->info.output_size = FFI_COMPLEXITY_OUTPUT;

    PyObject_GC_Track(ffi);
    return ffi;
}

static void ffi_dealloc(FFIObject *ffi)
{
    PyObject_GC_UnTrack(ffi);
    Py_DECREF(ffi->types_dict);
    Py_XDECREF(ffi->gc_wrefs);
    PyObject_GC_Del(ffi);
}

static int ffi_traverse(FFIObject *ffi, visitproc visit, void *arg)
{
    Py_VISIT(ffi->types_dict);
    Py_VISIT(ffi->gc_wrefs);
    return 0;
}

static PyObject *ffiobj_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    /* user-facing initialization code, for explicit FFI() calls */
    static const struct _cffi_type_context_s empty_ctx = { 0 };

    char *keywords[] = {NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwds, ":FFI", keywords))
        return NULL;

    return (PyObject *)ffi_internal_new(&empty_ctx);
}

#define ACCEPT_STRING   1
#define ACCEPT_CTYPE    2
#define ACCEPT_CDATA    4
#define ACCEPT_ALL      (ACCEPT_STRING | ACCEPT_CTYPE | ACCEPT_CDATA)

static CTypeDescrObject *_ffi_type(FFIObject *ffi, PyObject *arg,
                                   int accept)
{
    /* Returns the CTypeDescrObject from the user-supplied 'arg'.
       Does not return a new reference!
    */
    if ((accept & ACCEPT_STRING) && PyText_Check(arg)) {
        PyObject *x = PyDict_GetItem(ffi->types_dict, arg);
        if (x != NULL && CTypeDescr_Check(x))
            return (CTypeDescrObject *)x;

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
        PyObject *ct = realize_c_type(ffi->info.ctx,
                                      ffi->info.output, index);
        if (ct == NULL)
            return NULL;

        char *normalized_text = ((CTypeDescrObject *)ct)->ct_name;
        x = PyDict_GetItemString(ffi->types_dict, normalized_text);
        if (x == NULL) {
            PyDict_SetItemString(ffi->types_dict, normalized_text, ct);
        }
        else {
            Py_INCREF(x);
            Py_DECREF(ct);
            ct = x;
        }
        PyDict_SetItem(ffi->types_dict, arg, ct);
        return (CTypeDescrObject *)ct;
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

static PyObject *ffi_sizeof(FFIObject *self, PyObject *arg)
{
    CTypeDescrObject *ct = _ffi_type(self, arg, ACCEPT_ALL);
    if (ct == NULL)
        return NULL;

    if (ct->ct_size < 0) {
        PyErr_Format(FFIError, "don't know the size of ctype '%s'",
                     ct->ct_name);
        return NULL;
    }
    return PyInt_FromSsize_t(ct->ct_size);
}

static PyObject *ffi_typeof(FFIObject *self, PyObject *arg)
{
    PyObject *x = (PyObject *)_ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CDATA);
    if (x != NULL) {
        Py_INCREF(x);
    }
    else if (PyCFunction_Check(arg)) {
        abort(); // XXX
    }
    return x;
}

#if 0
static PyObject *ffi_new(ZefFFIObject *self, PyObject *args)
{
    CTypeDescrObject *ct, *ctitem;
    CDataObject *cd;
    PyObject *arg, *init = Py_None;
    Py_ssize_t dataoffset, datasize, explicitlength;
    if (!PyArg_ParseTuple(args, "O|O:new", &arg, &init))
        return NULL;

    ct = _ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CTYPE);
    if (ct == NULL)
        return NULL;

    explicitlength = -1;
    if (ct->ct_flags & (CT_POINTER | CT_STRUCT | CT_UNION)) {
        dataoffset = offsetof(CDataObject_own_nolength, alignment);
        ctitem = (ct->ct_flags & CT_POINTER) ? ct->ct_itemdescr : ct;
        datasize = ctitem->ct_size;
        if (datasize < 0) {
            PyErr_Format(PyExc_TypeError,
                         "cannot instantiate ctype '%s' of unknown size",
                         ctitem->ct_name);
            return NULL;
        }
        if (ctitem->ct_flags & CT_PRIMITIVE_CHAR)
            datasize *= 2;   /* forcefully add another character: a null */

        if ((ctitem->ct_flags & CT_WITH_VAR_ARRAY) && init != Py_None) {
            Py_ssize_t optvarsize = datasize;
            if (convert_struct_from_object(NULL,ctitem, init, &optvarsize) < 0)
                return NULL;
            datasize = optvarsize;
        }
    }
    else if (ct->ct_flags & CT_ARRAY) {
        dataoffset = offsetof(CDataObject_own_nolength, alignment);
        datasize = ct->ct_size;
        if (datasize < 0) {
            explicitlength = get_new_array_length(&init);
            if (explicitlength < 0)
                return NULL;
            ctitem = ct->ct_itemdescr;
            dataoffset = offsetof(CDataObject_own_length, alignment);
            datasize = explicitlength * ctitem->ct_size;
            if (explicitlength > 0 &&
                    (datasize / explicitlength) != ctitem->ct_size) {
                PyErr_SetString(PyExc_OverflowError,
                                "array size would overflow a Py_ssize_t");
                return NULL;
            }
        }
    }
    else if (ct->ct_flags & CT_PRIMITIVE_ANY) {
        cd = _new_casted_primitive(ct);
        datasize = ct->ct_size;
        goto initialize_casted_primitive;
    }
    else {
        PyErr_Format(PyExc_TypeError,
                     "cannot create cdata '%s' objects", ct->ct_name);
        return NULL;
    }

    cd = allocate_owning_object(dataoffset + datasize, ct);
    if (cd == NULL)
        return NULL;

    cd->c_data = ((char *)cd) + dataoffset;
    if (explicitlength >= 0)
        ((CDataObject_own_length*)cd)->length = explicitlength;

 initialize_casted_primitive:
    memset(cd->c_data, 0, datasize);
    if (init != Py_None) {
        if (convert_from_object(cd->c_data,
              (ct->ct_flags & CT_POINTER) ? ct->ct_itemdescr : ct, init) < 0) {
            Py_DECREF(cd);
            return NULL;
        }
    }
    return (PyObject *)cd;
}

static PyObject *ffi_cast(ZefFFIObject *self, PyObject *args)
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

static PyObject *ffi_string(ZefFFIObject *self, PyObject *args)
{
    CDataObject *cd;
    Py_ssize_t maxlen = -1;
    if (!PyArg_ParseTuple(args, "O!|n:string",
                          &CData_Type, &cd, &maxlen))
        return NULL;

    if (cd->c_type->ct_itemdescr != NULL &&
        cd->c_type->ct_itemdescr->ct_flags & (CT_PRIMITIVE_CHAR |
                                              CT_PRIMITIVE_SIGNED |
                                              CT_PRIMITIVE_UNSIGNED)) {
        Py_ssize_t length = maxlen;
        if (cd->c_data == NULL) {
            PyObject *s = cdata_repr(cd);
            if (s != NULL) {
                PyErr_Format(PyExc_RuntimeError,
                             "cannot use string() on %s",
                             PyText_AS_UTF8(s));
                Py_DECREF(s);
            }
            return NULL;
        }
        if (length < 0 && cd->c_type->ct_flags & CT_ARRAY) {
            length = get_array_length(cd);
        }
        if (cd->c_type->ct_itemdescr->ct_size == sizeof(char)) {
            const char *start = cd->c_data;
            if (length < 0) {
                /*READ(start, 1)*/
                length = strlen(start);
                /*READ(start, length)*/
            }
            else {
                const char *end;
                /*READ(start, length)*/
                end = (const char *)memchr(start, 0, length);
                if (end != NULL)
                    length = end - start;
            }
            return PyBytes_FromStringAndSize(start, length);
        }
    }
    else if (cd->c_type->ct_flags & CT_IS_ENUM) {
        abort();
        //return convert_cdata_to_enum_string(cd, 0);
    }
    else if (cd->c_type->ct_flags & CT_IS_BOOL) {
        /* fall through to TypeError */
    }
    else if (cd->c_type->ct_flags & (CT_PRIMITIVE_CHAR |
                                     CT_PRIMITIVE_SIGNED |
                                     CT_PRIMITIVE_UNSIGNED)) {
        /*READ(cd->c_data, cd->c_type->ct_size)*/
        if (cd->c_type->ct_size == sizeof(char))
            return PyBytes_FromStringAndSize(cd->c_data, 1);
    }
    PyErr_Format(PyExc_TypeError, "string(): unexpected cdata '%s' argument",
                 cd->c_type->ct_name);
    return NULL;
}

static CFieldObject *_ffi_field(CTypeDescrObject *ct, const char *fieldname)
{
    CFieldObject *cf;
    if (ct->ct_stuff == NULL) {
        PyErr_Format(PyExc_TypeError, "'%s' is incomplete", ct->ct_name);
        return NULL;
    }
    cf = (CFieldObject *)PyDict_GetItemString(ct->ct_stuff, fieldname);
    if (cf == NULL) {
        PyErr_Format(PyExc_KeyError, "'%s' has got no field '%s'",
                     ct->ct_name, fieldname);
        return NULL;
    }
    if (cf->cf_bitshift >= 0) {
        PyErr_SetString(PyExc_TypeError, "not supported for bitfields");
        return NULL;
    }
    return cf;
}

static PyObject *ffi_offsetof(ZefFFIObject *self, PyObject *args)
{
    PyObject *arg;
    char *fieldname;
    CTypeDescrObject *ct;
    CFieldObject *cf;

    if (!PyArg_ParseTuple(args, "Os:offsetof", &arg, &fieldname))
        return NULL;

    ct = _ffi_type(self, arg, ACCEPT_STRING|ACCEPT_CTYPE);
    if (ct == NULL)
        return NULL;

    if (!(ct->ct_flags & (CT_STRUCT|CT_UNION))) {
        PyErr_Format(PyExc_TypeError,
                     "expected a struct or union ctype, got '%s'",
                     ct->ct_name);
        return NULL;
    }
    cf = _ffi_field(ct, fieldname);
    if (cf == NULL)
        return NULL;
    return PyInt_FromSsize_t(cf->cf_offset);
}

static PyObject *ffi_addressof(ZefFFIObject *self, PyObject *args)
{
    PyObject *obj;
    char *fieldname = NULL;

    if (!PyArg_ParseTuple(args, "O|z:addressof", &obj, &fieldname))
        return NULL;

    if (CData_Check(obj)) {
        CDataObject *cd = (CDataObject *)obj;
        CTypeDescrObject *ct;
        Py_ssize_t offset;

        ct = cd->c_type;
        if (fieldname != NULL && ct->ct_flags & CT_POINTER)
            ct = ct->ct_itemdescr;

        if (!(ct->ct_flags & (CT_STRUCT|CT_UNION))) {
            PyErr_Format(PyExc_TypeError,
                         "expected a struct or union cdata, got '%s'",
                         ct->ct_name);
            return NULL;
        }

        if (fieldname == NULL) {
            offset = 0;
        }
        else {
            CFieldObject *cf = _ffi_field(ct, fieldname);
            if (cf == NULL)
                return NULL;
            offset = cf->cf_offset;
            ct = cf->cf_type;
        }
        ct = fetch_pointer_type(self->types_dict, ct);
        if (ct == NULL)
            return NULL;
        return new_simple_cdata(cd->c_data + offset, ct);
    }
    else if (ZefLib_Check(obj)) {
        PyObject *attr, *name;
        char *reason;

        if (fieldname == NULL) {
            PyErr_SetString(PyExc_TypeError, "addressof(Lib, fieldname) "
                            "cannot be used with only one argument");
            return NULL;
        }
        name = PyString_FromString(fieldname);
        if (name == NULL)
            return NULL;
        attr = lib_findattr((ZefLibObject *)obj, name, ZefError);
        Py_DECREF(name);
        if (attr == NULL)
            return NULL;

        if (ZefGlobSupport_Check(attr)) {
            return addressof_global_var((ZefGlobSupportObject *)attr);
        }

        if (PyCFunction_Check(attr))
            reason = "declare that function as a function pointer instead";
        else
            reason = "numeric constants don't have addresses";

        PyErr_Format(PyExc_TypeError,
                     "cannot take the address of '%s' (%s)",
                     fieldname, reason);
        return NULL;
    }
    else {
        PyErr_SetString(PyExc_TypeError, "addressof() first argument must be "
                        "a cdata struct or union, a pointer to one, or a Lib "
                        "object");
        return NULL;
    }
}

static PyObject *ffi_getctype(ZefFFIObject *self, PyObject *args)
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
                 ((ct->ct_flags & (CT_ARRAY | CT_FUNCTION)) != 0));
    add_space = (!add_paren && replace_with_len > 0 &&
                 replace_with[0] != '[' && replace_with[0] != '(');

    res = combine_type_name_l(ct, replace_with_len + add_space + 2 * add_paren);
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

static PyObject *ffi_new_handle(ZefFFIObject *self, PyObject *arg)
{
    CTypeDescrObject *ct = ZefNULL->c_type;   // <ctype 'void *'>
    CDataObject *cd;

    cd = (CDataObject *)PyObject_GC_New(CDataObject, &CDataOwningGC_Type);
    if (cd == NULL)
        return NULL;
    Py_INCREF(ct);
    cd->c_type = ct;
    Py_INCREF(arg);
    cd->c_data = ((char *)arg) - 42;
    cd->c_weakreflist = NULL;
    PyObject_GC_Track(cd);
    return (PyObject *)cd;
}

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

static PyObject *ffi_gc(ZefFFIObject *self, PyObject *args)
{
    CDataObject *cd;
    PyObject *destructor;

    if (!PyArg_ParseTuple(args, "O!O:gc", &CData_Type, &cd, &destructor))
        return NULL;

    return gc_weakrefs_build(self, cd, destructor);
}
#endif

static PyMethodDef ffi_methods[] = {
#if 0
    {"addressof",     (PyCFunction)ffi_addressof, METH_VARARGS},
    {"cast",          (PyCFunction)ffi_cast,      METH_VARARGS},
    {"close_library", ffi_close_library,          METH_VARARGS | METH_STATIC},
    {"from_handle",   (PyCFunction)ffi_from_handle,METH_O},
    {"gc",            (PyCFunction)ffi_gc,        METH_VARARGS},
    {"getctype",      (PyCFunction)ffi_getctype,  METH_VARARGS},
    {"load_library",  (PyCFunction)ffi_load_library,METH_VARARGS|METH_KEYWORDS},
    {"offsetof",      (PyCFunction)ffi_offsetof,  METH_VARARGS},
    {"new",           (PyCFunction)ffi_new,       METH_VARARGS},
    {"new_handle",    (PyCFunction)ffi_new_handle,METH_O},
#endif
    {"sizeof",        (PyCFunction)ffi_sizeof,    METH_O},
#if 0
    {"string",        (PyCFunction)ffi_string,    METH_VARARGS},
#endif
    {"typeof",        (PyCFunction)ffi_typeof,    METH_O},
    {NULL}
};

static PyTypeObject FFI_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "cffi.FFI",
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
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_HAVE_GC,    /* tp_flags */
    0,                                          /* tp_doc */
    (traverseproc)ffi_traverse,                 /* tp_traverse */
    0,                                          /* tp_clear */
    0,                                          /* tp_richcompare */
    0,                                          /* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    ffi_methods,                                /* tp_methods */
    0,                                          /* tp_members */
    0,                                          /* tp_getset */
    0,                                          /* tp_base */
    0,                                          /* tp_dict */
    0,                                          /* tp_descr_get */
    0,                                          /* tp_descr_set */
    0,                                          /* tp_dictoffset */
    0,                                          /* tp_init */
    0,                                          /* tp_alloc */
    ffiobj_new,                                 /* tp_new */
    PyObject_GC_Del,                            /* tp_free */
};
