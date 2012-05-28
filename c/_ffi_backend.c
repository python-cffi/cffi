#include <Python.h>
#include <stddef.h>
#include <stdint.h>
#include <dlfcn.h>

/************************************************************/

#define CT_PRIMITIVE_SIGNED   1
#define CT_PRIMITIVE_UNSIGNED 2
#define CT_PRIMITIVE_CHAR     4
#define CT_PRIMITIVE_FLOAT    8
#define CT_POINTER           16
#define CT_ARRAY             32
#define CT_STRUCT            64

#define CT_PRIMITIVE_FITS_LONG    128
#define CT_PRIMITIVE_ANY  (CT_PRIMITIVE_SIGNED |        \
                           CT_PRIMITIVE_UNSIGNED |      \
                           CT_PRIMITIVE_CHAR |          \
                           CT_PRIMITIVE_FLOAT)

typedef struct _ctypedescr {
    PyObject_VAR_HEAD

    struct _ctypedescr *ct_itemdescr;  /* ptrs and arrays: the item type */
    PyObject *ct_fields;               /* dict of the fields */

    Py_ssize_t ct_size;     /* size of instances, or -1 if unknown */
    int ct_flags;           /* CT_xxx flags */

    int ct_name_position;   /* index in ct_name of where to put a var name */
    char ct_name[1];        /* string, e.g. "int *" for pointers to ints */
} CTypeDescrObject;

typedef struct {
    PyObject_HEAD
    CTypeDescrObject *c_type;
    char *c_data;
} CDataObject;

static PyTypeObject CTypeDescr_Type;
static PyTypeObject CData_Type;
static PyTypeObject CDataOwning_Type;

#define CTypeDescr_Check(ob)  (Py_TYPE(ob) == &CTypeDescr_Type)
#define CData_Check(ob)       (Py_TYPE(ob) == &CData_Type ||            \
                               Py_TYPE(ob) == &CDataOwning_Type)

typedef union {
    unsigned char m_char;
    unsigned short m_short;
    unsigned int m_int;
    unsigned long m_long;
    unsigned long long m_longlong;
    float m_float;
    double m_double;
} union_alignment;

typedef struct {
    CDataObject head;
    union_alignment alignment;
} CDataObject_with_alignment;

typedef struct {
    CDataObject head;
    Py_ssize_t length;
    union_alignment alignment;
} CDataObject_with_length;

/************************************************************/

static CTypeDescrObject *
ctypedescr_new(int name_size)
{
    CTypeDescrObject *ct = PyObject_GC_NewVar(CTypeDescrObject,
                                              &CTypeDescr_Type,
                                              name_size);
    if (ct == NULL)
        return NULL;

    ct->ct_itemdescr = NULL;
    ct->ct_fields = NULL;
    PyObject_GC_Track(ct);
    return ct;
}

static CTypeDescrObject *
ctypedescr_new_on_top(CTypeDescrObject *ct_base, const char *extra_text,
                      int extra_position)
{
    int base_name_len = strlen(ct_base->ct_name);
    int extra_name_len = strlen(extra_text);
    CTypeDescrObject *ct = ctypedescr_new(base_name_len + extra_name_len + 1);
    char *p;
    if (ct == NULL)
        return NULL;

    Py_INCREF(ct_base);
    ct->ct_itemdescr = ct_base;
    ct->ct_name_position = ct_base->ct_name_position + extra_position;

    p = ct->ct_name;
    memcpy(p, ct_base->ct_name, ct_base->ct_name_position);
    p += ct_base->ct_name_position;
    memcpy(p, extra_text, extra_name_len);
    p += extra_name_len;
    memcpy(p, ct_base->ct_name + ct_base->ct_name_position,
           base_name_len - ct_base->ct_name_position + 1);

    return ct;
}

static PyObject *
ctypedescr_repr(CTypeDescrObject *ct)
{
    return PyString_FromFormat("<ctype '%s'>", ct->ct_name);
}

static void
ctypedescr_dealloc(CTypeDescrObject *ct)
{
    PyObject_GC_UnTrack(ct);
    Py_XDECREF(ct->ct_itemdescr);
    Py_XDECREF(ct->ct_fields);
    Py_TYPE(ct)->tp_free((PyObject *)ct);
}

static int
ctypedescr_traverse(CTypeDescrObject *ct, visitproc visit, void *arg)
{
    Py_VISIT(ct->ct_itemdescr);
    Py_VISIT(ct->ct_fields);
    return 0;
}

static int
ctypedescr_clear(CTypeDescrObject *ct)
{
    Py_CLEAR(ct->ct_itemdescr);
    Py_CLEAR(ct->ct_fields);
    return 0;
}

static PyTypeObject CTypeDescr_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.CTypeDescr",
    offsetof(CTypeDescrObject, ct_name),
    sizeof(char),
    (destructor)ctypedescr_dealloc,             /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    (reprfunc)ctypedescr_repr,                  /* tp_repr */
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
    (traverseproc)ctypedescr_traverse,          /* tp_traverse */
    (inquiry)ctypedescr_clear,                  /* tp_clear */
};

/************************************************************/

static PY_LONG_LONG
read_raw_signed_data(char *target, int size)
{
    if (size == sizeof(signed char))
        return *((signed char*)target);
    else if (size == sizeof(short))
        return *((short*)target);
    else if (size == sizeof(int))
        return *((int*)target);
    else if (size == sizeof(long))
        return *((long*)target);
    else if (size == sizeof(PY_LONG_LONG))
        return *((PY_LONG_LONG*)target);
    else {
        Py_FatalError("read_raw_signed_data: bad integer size");
        return 0;
    }
}

static unsigned PY_LONG_LONG
read_raw_unsigned_data(char *target, int size)
{
    if (size == sizeof(unsigned char))
        return *((unsigned char*)target);
    else if (size == sizeof(unsigned short))
        return *((unsigned short*)target);
    else if (size == sizeof(unsigned int))
        return *((unsigned int*)target);
    else if (size == sizeof(unsigned long))
        return *((unsigned long*)target);
    else if (size == sizeof(unsigned PY_LONG_LONG))
        return *((unsigned PY_LONG_LONG*)target);
    else {
        Py_FatalError("read_raw_unsigned_data: bad integer size");
        return 0;
    }
}

static void
write_raw_integer_data(char *target, unsigned PY_LONG_LONG source, int size)
{
    if (size == sizeof(unsigned char))
        *((unsigned char*)target) = source;
    else if (size == sizeof(unsigned short))
        *((unsigned short*)target) = source;
    else if (size == sizeof(unsigned int))
        *((unsigned int*)target) = source;
    else if (size == sizeof(unsigned long))
        *((unsigned long*)target) = source;
    else if (size == sizeof(unsigned PY_LONG_LONG))
        *((unsigned PY_LONG_LONG*)target) = source;
    else
        Py_FatalError("write_raw_integer_data: bad integer size");
}

static PyObject *
convert_to_object(char *data, CTypeDescrObject *ct)
{
    if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        PY_LONG_LONG value =
            read_raw_signed_data(data, ct->ct_size);

        if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
            return PyInt_FromLong((long)value);
        else
            return PyLong_FromLongLong(value);
    }
    else if (ct->ct_flags & CT_PRIMITIVE_UNSIGNED) {
        unsigned PY_LONG_LONG value =
            read_raw_unsigned_data(data, ct->ct_size);

        if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
            return PyInt_FromLong((long)value);
        else
            return PyLong_FromUnsignedLongLong(value);
    }
    else {
        fprintf(stderr, "convert_to_object: '%s'\n", ct->ct_name);
        Py_FatalError("convert_to_object");
        return NULL;
    }
}

static int
convert_from_object(char *data, CTypeDescrObject *ct, PyObject *init)
{
    PyObject *s;

    if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        PY_LONG_LONG value;
        if (PyInt_Check(init))
            value = PyInt_AsLong(init);
        else
            value = PyLong_AsLongLong(init);

        if (value == -1 && PyErr_Occurred())
            return -1;
        write_raw_integer_data(data, value, ct->ct_size);
        if (value != read_raw_signed_data(data, ct->ct_size))
            goto overflow;
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_UNSIGNED) {
        unsigned PY_LONG_LONG value;
        if (PyInt_Check(init)) {
            long value1 = PyInt_AsLong(init);
            if (value1 < 0) {
                if (PyErr_Occurred())
                    return -1;
                goto overflow;
            }
            value = value1;
        }
        else {
            value = PyLong_AsUnsignedLongLong(init);
            if (value == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred())
                return -1;
        }
        write_raw_integer_data(data, value, ct->ct_size);
        if (value != read_raw_unsigned_data(data, ct->ct_size))
            goto overflow;
        return 0;
    }
    fprintf(stderr, "convert_from_object: '%s'\n", ct->ct_name);
    Py_FatalError("convert_from_object");
    return -1;

 overflow:
    s = PyObject_Str(init);
    if (s == NULL)
        return -1;
    PyErr_Format(PyExc_OverflowError, "integer %s does not fit '%s'",
                 PyString_AS_STRING(s), ct->ct_name);
    Py_DECREF(s);
    return -1;
}

static Py_ssize_t cdata_size(CDataObject *cd)
{
    if (cd->c_type->ct_size >= 0)
        return cd->c_type->ct_size;
    else
        return ((CDataObject_with_length *)cd)->length;
}

static void cdata_dealloc(CDataObject *cd)
{
    Py_DECREF(cd->c_type);
    PyObject_Del(cd);
}

static int cdata_traverse(CDataObject *cd, visitproc visit, void *arg)
{
    Py_VISIT(cd->c_type);
    return 0;
}

static PyObject *cdata_repr(CDataObject *cd)
{
    return PyString_FromFormat("<cdata '%s'>", cd->c_type->ct_name);
}

static PyObject *cdataowning_repr(CDataObject *cd)
{
    Py_ssize_t size;
    if (cd->c_type->ct_flags & CT_POINTER)
        size = cd->c_type->ct_itemdescr->ct_size;
    else
        size = cdata_size(cd);
    return PyString_FromFormat("<cdata '%s' owning %zd bytes>",
                               cd->c_type->ct_name, size);
}

static int cdata_nonzero(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_ANY) {
        /* ... */
        unsigned PY_LONG_LONG value;
        value = read_raw_unsigned_data(cd->c_data, cd->c_type->ct_size);
        return value != 0;
    }
    return cd->c_data != NULL;
}

static PyObject *cdata_int(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_ANY) {
        /* ... */
        return convert_to_object(cd->c_data, cd->c_type);
    }
    PyErr_Format(PyExc_TypeError, "int() not supported on cdata '%s'",
                 cd->c_type->ct_name);
    return NULL;
}

static PyObject *cdata_richcompare(PyObject *v, PyObject *w, int op)
{
    CDataObject *obv, *obw;
    int equal;

    if (op != Py_EQ && op != Py_NE)
        goto Unimplemented;

    assert(CData_Check(v));
    if (!CData_Check(w))
        goto Unimplemented;

    obv = (CDataObject *)v;
    obw = (CDataObject *)w;
    if (obv->c_type != obw->c_type) {
        equal = 0;
    }
    else if (obv == obw) {
        equal = 1;
    }
    else if (obv->c_type->ct_flags & CT_PRIMITIVE_FLOAT) {
        Py_FatalError("XXX");
    }
    else if (obv->c_type->ct_flags & CT_PRIMITIVE_ANY) {
        equal = (memcmp(obv->c_data, obw->c_data, obv->c_type->ct_size) == 0);
    }
    else
        equal = 0;

    return (equal ^ (op == Py_NE)) ? Py_True : Py_False;

 Unimplemented:
    Py_INCREF(Py_NotImplemented);
    return Py_NotImplemented;
}

static long cdata_hash(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_ANY) {
        long result;
        unsigned PY_LONG_LONG value;
        value = read_raw_unsigned_data(cd->c_data, cd->c_type->ct_size);

        result = (long) value;
#if SIZE_OF_LONG_LONG > SIZE_OF_LONG
        value >>= (8 * SIZE_OF_LONG);
        result ^= value * 1000003;
#endif
        result = _Py_HashPointer(cd->c_type) + result * 1000003;
        if (result == -1)
            result = -2;
        return result;
    }
    else {
        return _Py_HashPointer(cd);
    }
}

static Py_ssize_t
cdata_length(CDataObject *cd)
{
    PyErr_Format(PyExc_TypeError, "cdata of type '%s' has no len()",
                 cd->c_type->ct_name);
    return -1;
}

static PyObject *
cdata_subscript(CDataObject *cd, PyObject *key)
{
    /* use 'mp_subscript' instead of 'sq_item' because we don't want
       negative indexes to be corrected automatically */
    Py_ssize_t i = PyNumber_AsSsize_t(key, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred())
        return NULL;

    if (cd->c_type->ct_flags & CT_POINTER) {
        if (i != 0) {
            PyErr_Format(PyExc_IndexError,
                         "cdata '%s' can only be indexed by 0",
                         cd->c_type->ct_name);
            return NULL;
        }
        return convert_to_object(cd->c_data, cd->c_type->ct_itemdescr);
    }

    PyErr_Format(PyExc_TypeError, "cdata of type '%s' cannot be indexed",
                 cd->c_type->ct_name);
    return NULL;
}

static int
cdata_ass_sub(CDataObject *cd, PyObject *key, PyObject *v)
{
    /* use 'mp_ass_subscript' instead of 'sq_ass_item' because we don't want
       negative indexes to be corrected automatically */
    Py_ssize_t i = PyNumber_AsSsize_t(key, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred())
        return -1;

    if (cd->c_type->ct_flags & CT_POINTER) {
        if (i != 0) {
            PyErr_Format(PyExc_IndexError,
                         "cdata '%s' can only be indexed by 0",
                         cd->c_type->ct_name);
            return -1;
        }
        return convert_from_object(cd->c_data, cd->c_type->ct_itemdescr, v);
    }

    PyErr_Format(PyExc_TypeError,
                 "cdata of type '%s' does not support index assignment",
                 cd->c_type->ct_name);
    return -1;
}

static PyNumberMethods CData_as_number = {
    0,                          /*nb_add*/
    0,                          /*nb_subtract*/
    0,                          /*nb_multiply*/
    0,                          /*nb_divide*/
    0,                          /*nb_remainder*/
    0,                          /*nb_divmod*/
    0,                          /*nb_power*/
    0,                          /*nb_negative*/
    0,                          /*nb_positive*/
    0,                          /*nb_absolute*/
    (inquiry)cdata_nonzero,     /*nb_nonzero*/
    0,                          /*nb_invert*/
    0,                          /*nb_lshift*/
    0,                          /*nb_rshift*/
    0,                          /*nb_and*/
    0,                          /*nb_xor*/
    0,                          /*nb_or*/
    0,                          /*nb_coerce*/
    (unaryfunc)cdata_int,       /*nb_int*/
    0,                          /*nb_long*/
    0,                          /*nb_float*/
    0,                          /*nb_oct*/
    0,                          /*nb_hex*/
};

static PyMappingMethods CData_as_mapping = {
    (lenfunc)cdata_length, /*mp_length*/
    (binaryfunc)cdata_subscript, /*mp_subscript*/
    (objobjargproc)cdata_ass_sub, /*mp_ass_subscript*/
};

static PyTypeObject CData_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.CData",
    sizeof(CDataObject),
    0,
    (destructor)cdata_dealloc,                  /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    (reprfunc)cdata_repr,                       /* tp_repr */
    &CData_as_number,                           /* tp_as_number */
    0,                                          /* tp_as_sequence */
    &CData_as_mapping,                          /* tp_as_mapping */
    (hashfunc)cdata_hash,                       /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    PyObject_GenericGetAttr,                    /* tp_getattro */
    0,                                          /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                         /* tp_flags */
    0,                                          /* tp_doc */
    (traverseproc)cdata_traverse,               /* tp_traverse */
    0,                                          /* tp_clear */
    cdata_richcompare,                          /* tp_richcompare */
};

static PyTypeObject CDataOwning_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.CDataOwning",
    sizeof(CDataObject),
    0,
    0,                                          /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    (reprfunc)cdataowning_repr,                 /* tp_repr */
    0,                                          /* tp_as_number */
    0,                                          /* tp_as_sequence */
    0,                                          /* tp_as_mapping */
    0,                                          /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    0,                                          /* tp_getattro */
    0,                                          /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                         /* tp_flags */
    0,                                          /* tp_doc */
    0,                                          /* tp_traverse */
    0,                                          /* tp_clear */
    0,                                          /* tp_richcompare */
    0,                                          /* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    0,                                          /* tp_methods */
    0,                                          /* tp_members */
    0,                                          /* tp_getset */
    &CData_Type,                                /* tp_base */
};

static PyObject *b_new(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct, *ctitem;
    CDataObject *cd;
    PyObject *init;
    Py_ssize_t size;
    if (!PyArg_ParseTuple(args, "O!O:new", &CTypeDescr_Type, &ct, &init))
        return NULL;

    ctitem = ct->ct_itemdescr;
    if (ctitem == NULL) {
        PyErr_SetString(PyExc_TypeError, "expected a pointer or array ctype");
        return NULL;
    }
    if (ctitem->ct_size < 0) {
        PyErr_Format(PyExc_TypeError,
                     "cannot instantiate ctype '%s' of unknown size",
                     ctitem->ct_name);
        return NULL;
    }

    size = offsetof(CDataObject_with_alignment, alignment) + ctitem->ct_size;
    cd = (CDataObject *)PyObject_Malloc(size);
    if (PyObject_Init((PyObject *)cd, &CDataOwning_Type) == NULL)
        return NULL;

    Py_INCREF(ct);
    cd->c_type = ct;
    cd->c_data = ((char *)cd) +
        offsetof(CDataObject_with_alignment, alignment);

    memset(cd->c_data, 0, ctitem->ct_size);
    if (init != Py_None) {
        if (convert_from_object(cd->c_data,
                                (ct->ct_flags & CT_POINTER) ? ctitem : ct,
                                init) < 0) {
            Py_DECREF(cd);
            return NULL;
        }
    }
    return (PyObject *)cd;
}

static PyObject *b_cast(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    CDataObject *cd, *cdsrc;
    PyObject *ob;
    if (!PyArg_ParseTuple(args, "O!O:cast", &CTypeDescr_Type, &ct, &ob))
        return NULL;

    if (ct->ct_flags & CT_POINTER) {
        /* cast to a pointer */
        if (!CData_Check(ob))
            goto cannot_cast;

        cdsrc = (CDataObject *)ob;
        if (!(cdsrc->c_type->ct_flags & CT_POINTER))
            goto cannot_cast;

        cd = PyObject_New(CDataObject, &CData_Type);
        if (cd == NULL)
            return NULL;

        cd->c_data = cdsrc->c_data;
    }
    else if (ct->ct_flags & CT_PRIMITIVE_ANY) {
        /* cast to a primitive */
        unsigned PY_LONG_LONG value;
        int size;

        if (PyInt_Check(ob))
            value = (unsigned PY_LONG_LONG)PyInt_AS_LONG(ob);
        else if (PyLong_Check(ob))
            value = PyLong_AsUnsignedLongLongMask(ob);
        else
            goto cannot_cast;

        size = offsetof(CDataObject_with_alignment, alignment) + ct->ct_size;
        cd = (CDataObject *)PyObject_Malloc(size);
        if (PyObject_Init((PyObject *)cd, &CData_Type) == NULL)
            return NULL;

        cd->c_data = ((char *)cd) +
            offsetof(CDataObject_with_alignment, alignment);
        write_raw_integer_data(cd->c_data, value, ct->ct_size);
    }
    else
        goto cannot_cast;

    Py_INCREF(ct);
    cd->c_type = ct;
    return (PyObject *)cd;

 cannot_cast:
    if (CData_Check(ob))
        PyErr_Format(PyExc_TypeError, "cannot cast ctype '%s' to ctype '%s'",
                     ((CDataObject *)ob)->c_type->ct_name, ct->ct_name);
    else
        PyErr_Format(PyExc_TypeError, "cannot cast '%s' object to ctype '%s'",
                     Py_TYPE(ob)->tp_name, ct->ct_name);
    return NULL;
}

/************************************************************/

typedef struct {
    PyObject_HEAD
    void *dl_handle;
} dlobject;

static void dl_dealloc(dlobject *dlobj)
{
    dlclose(dlobj->dl_handle);
    PyObject_Del(dlobj);
}

static PyObject *dl_load_function(dlobject *dlobj, PyObject *args)
{
    /* XXX */
    return NULL;
}

static PyMethodDef dl_methods[] = {
    {"load_function",   (PyCFunction)dl_load_function,  METH_VARARGS},
    {NULL,              NULL}           /* sentinel */
};

static PyTypeObject dl_type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.Library",             /* tp_name */
    sizeof(dlobject),                   /* tp_basicsize */
    0,                                  /* tp_itemsize */
    /* methods */
    (destructor)dl_dealloc,             /* tp_dealloc */
    0,                                  /* tp_print */
    0,                                  /* tp_getattr */
    0,                                  /* tp_setattr */
    0,                                  /* tp_compare */
    0,                                  /* tp_repr */
    0,                                  /* tp_as_number */
    0,                                  /* tp_as_sequence */
    0,                                  /* tp_as_mapping */
    0,                                  /* tp_hash */
    0,                                  /* tp_call */
    0,                                  /* tp_str */
    PyObject_GenericGetAttr,            /* tp_getattro */
    0,                                  /* tp_setattro */
    0,                                  /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                 /* tp_flags */
    0,                                  /* tp_doc */
    0,                                  /* tp_traverse */
    0,                                  /* tp_clear */
    0,                                  /* tp_richcompare */
    0,                                  /* tp_weaklistoffset */
    0,                                  /* tp_iter */
    0,                                  /* tp_iternext */
    dl_methods,                         /* tp_methods */
};

static PyObject *b_load_library(PyObject *self, PyObject *args)
{
    char *filename;
    void *handle;
    dlobject *dlobj;

    if (!PyArg_ParseTuple(args, "et:load_library",
                          Py_FileSystemDefaultEncoding, &filename))
        return NULL;

    handle = dlopen(filename, RTLD_LAZY);
    if (handle == NULL) {
        char buf[200];
        PyOS_snprintf(buf, sizeof(buf), "cannot load library: %s", filename);
        PyErr_SetString(PyExc_OSError, buf);
        return NULL;
    }

    dlobj = PyObject_New(dlobject, &dl_type);
    if (dlobj == NULL) {
        dlclose(handle);
        return NULL;
    }
    dlobj->dl_handle = handle;
    return (PyObject *)dlobj;
}

/************************************************************/

static PyObject *b_nonstandard_integer_types(PyObject *self, PyObject *noarg)
{
#define UNSIGNED   0x1000
    static const struct descr_s { const char *name; int size; } types[] = {
        { "int8_t",        1 },
        { "uint8_t",       1 | UNSIGNED },
        { "int16_t",       2 },
        { "uint16_t",      2 | UNSIGNED },
        { "int32_t",       4 },
        { "uint32_t",      4 | UNSIGNED },
        { "int64_t",       8 },
        { "uint64_t",      8 | UNSIGNED },

        { "intptr_t",      sizeof(intptr_t) },
        { "uintptr_t",     sizeof(uintptr_t) | UNSIGNED },
        { "ptrdiff_t",     sizeof(ptrdiff_t) },
        { "size_t",        sizeof(size_t) | UNSIGNED },
        { "ssize_t",       sizeof(ssize_t) },
        { "wchar_t",       sizeof(wchar_t) | UNSIGNED },
        { NULL }
    };
#undef UNSIGNED
    const struct descr_s *ptypes;
    PyObject *d;

    d = PyDict_New();
    if (d == NULL)
        return NULL;

    for (ptypes=types; ptypes->name; ptypes++) {
        int err;
        PyObject *obj = PyInt_FromLong(ptypes->size);
        if (obj == NULL)
            goto error;
        err = PyDict_SetItemString(d, ptypes->name, obj);
        Py_DECREF(obj);
        if (err != 0)
            goto error;
    }
    return d;

 error:
    Py_DECREF(d);
    return NULL;
}

static PyObject *b_new_primitive_type(PyObject *self, PyObject *args)
{
    PyObject *ffi;
    CTypeDescrObject *td;
    const char *name;
    static const struct descr_s { const char *name; int size, flags; }
    types[] = {
        { "char", sizeof(char), CT_PRIMITIVE_CHAR },
        { "short", sizeof(short), CT_PRIMITIVE_SIGNED },
        { "int", sizeof(int), CT_PRIMITIVE_SIGNED },
        { "long", sizeof(long), CT_PRIMITIVE_SIGNED },
        { "long long", sizeof(long long), CT_PRIMITIVE_SIGNED },
        { "signed char", sizeof(signed char), CT_PRIMITIVE_SIGNED },
        { "unsigned char", sizeof(unsigned char), CT_PRIMITIVE_UNSIGNED },
        { "unsigned short", sizeof(unsigned short), CT_PRIMITIVE_UNSIGNED },
        { "unsigned int", sizeof(unsigned int), CT_PRIMITIVE_UNSIGNED },
        { "unsigned long", sizeof(unsigned long), CT_PRIMITIVE_UNSIGNED },
        { "unsigned long long", sizeof(unsigned long long), CT_PRIMITIVE_UNSIGNED },
        { "float", sizeof(float), CT_PRIMITIVE_FLOAT },
        { "double", sizeof(double), CT_PRIMITIVE_FLOAT },
        { NULL }
    };
    const struct descr_s *ptypes;
    int name_size;

    if (!PyArg_ParseTuple(args, "Os:new_primitive_type", &ffi, &name))
        return NULL;

    for (ptypes=types; ; ptypes++) {
        if (ptypes->name == NULL) {
            PyErr_SetString(PyExc_KeyError, name);
            return NULL;
        }
        if (strcmp(name, ptypes->name) == 0)
            break;
    }

    name_size = strlen(ptypes->name) + 1;
    td = ctypedescr_new(name_size);
    if (td == NULL)
        return NULL;

    memcpy(td->ct_name, name, name_size);
    td->ct_itemdescr = NULL;
    td->ct_fields = NULL;
    td->ct_size = ptypes->size;
    td->ct_flags = ptypes->flags;
    if (td->ct_flags & CT_PRIMITIVE_SIGNED) {
        if (td->ct_size <= sizeof(long))
            td->ct_flags |= CT_PRIMITIVE_FITS_LONG;
    }
    else if (td->ct_flags & (CT_PRIMITIVE_UNSIGNED | CT_PRIMITIVE_CHAR)) {
        if (td->ct_size < sizeof(long))
            td->ct_flags |= CT_PRIMITIVE_FITS_LONG;
    }
    td->ct_name_position = strlen(td->ct_name);
    return (PyObject *)td;
}

static PyObject *b_new_pointer_type(PyObject *self, PyObject *args)
{
    PyObject *ffi;
    CTypeDescrObject *td, *ctitem;

    if (!PyArg_ParseTuple(args, "OO!:new_pointer_type",
                          &ffi, &CTypeDescr_Type, &ctitem))
        return NULL;

    td = ctypedescr_new_on_top(ctitem, " *", 2);
    if (td == NULL)
        return NULL;

    td->ct_size = sizeof(void *);
    td->ct_flags = CT_POINTER;
    return (PyObject *)td;
}

static PyObject *b_sizeof_type(PyObject *self, PyObject *arg)
{
    if (!CTypeDescr_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected a 'ctype' object");
        return NULL;
    }
    if (((CTypeDescrObject *)arg)->ct_size < 0) {
        PyErr_Format(PyExc_ValueError, "ctype '%s' is of unknown size",
                     ((CTypeDescrObject *)arg)->ct_name);
        return NULL;
    }
    return PyInt_FromLong(((CTypeDescrObject *)arg)->ct_size);
}

static PyMethodDef FFIBackendMethods[] = {
    {"nonstandard_integer_types", b_nonstandard_integer_types, METH_NOARGS},
    {"load_library", b_load_library, METH_VARARGS},
    {"new_primitive_type", b_new_primitive_type, METH_VARARGS},
    {"new_pointer_type", b_new_pointer_type, METH_VARARGS},
    {"new", b_new, METH_VARARGS},
    {"cast", b_cast, METH_VARARGS},
    {"sizeof_type", b_sizeof_type, METH_O},
    {NULL,     NULL}	/* Sentinel */
};

void init_ffi_backend(void)
{
    PyObject *m, *v;

    v = PySys_GetObject("version");
    if (v == NULL || !PyString_Check(v) ||
            strncmp(PyString_AS_STRING(v), PY_VERSION, 3) != 0) {
        PyErr_Format(PyExc_ImportError,
                     "this module was compiled for Python %c%c%c",
                     PY_VERSION[0], PY_VERSION[1], PY_VERSION[2]);
        return;
    }

    m = Py_InitModule("_ffi_backend", FFIBackendMethods);
    if (PyType_Ready(&dl_type) < 0)
        return;
    if (PyType_Ready(&CTypeDescr_Type) < 0)
        return;
    if (PyType_Ready(&CData_Type) < 0)
        return;
    if (PyType_Ready(&CDataOwning_Type) < 0)
        return;
}
