#include <Python.h>
#include "structmember.h"

#include <stddef.h>
#include <stdint.h>
#include <dlfcn.h>

#include <ffi.h>

/************************************************************/

#define CT_PRIMITIVE_SIGNED   1
#define CT_PRIMITIVE_UNSIGNED 2
#define CT_PRIMITIVE_CHAR     4
#define CT_PRIMITIVE_FLOAT    8
#define CT_POINTER           16
#define CT_ARRAY             32
#define CT_STRUCT            64
#define CT_UNION            128
#define CT_FUNCTIONPTR      256
#define CT_VOID             512

#define CT_CAST_ANYTHING         1024    /* 'char' and 'void' only */
#define CT_PRIMITIVE_FITS_LONG   2048
#define CT_OPAQUE                4096
#define CT_PRIMITIVE_ANY  (CT_PRIMITIVE_SIGNED |        \
                           CT_PRIMITIVE_UNSIGNED |      \
                           CT_PRIMITIVE_CHAR |          \
                           CT_PRIMITIVE_FLOAT)

typedef struct _ctypedescr {
    PyObject_VAR_HEAD

    struct _ctypedescr *ct_itemdescr;  /* ptrs and arrays: the item type */
    PyObject *ct_stuff;                /* structs: dict of the fields
                                          arrays: ctypedescr of the ptr type
                                          function: tuple(ctres, ctargs...) */
    void *ct_extra;                    /* structs: first field (not a ref!)
                                          function types: cif_description
                                          primitives: prebuilt "cif" object */

    Py_ssize_t ct_size;     /* size of instances, or -1 if unknown */
    Py_ssize_t ct_length;   /* length of arrays, or -1 if unknown;
                               or alignment of primitive and struct types */
    int ct_flags;           /* CT_xxx flags */

    int ct_name_position;   /* index in ct_name of where to put a var name */
    char ct_name[1];        /* string, e.g. "int *" for pointers to ints */
} CTypeDescrObject;

typedef struct {
    PyObject_HEAD
    CTypeDescrObject *c_type;
    char *c_data;
} CDataObject;

typedef struct cfieldobject_s {
    PyObject_HEAD
    CTypeDescrObject *cf_type;
    Py_ssize_t cf_offset;
    int cf_bitsize;
    struct cfieldobject_s *cf_next;
} CFieldObject;

static PyTypeObject CTypeDescr_Type;
static PyTypeObject CField_Type;
static PyTypeObject CData_Type;
static PyTypeObject CDataOwning_Type;

#define CTypeDescr_Check(ob)  (Py_TYPE(ob) == &CTypeDescr_Type)
#define CData_Check(ob)       (Py_TYPE(ob) == &CData_Type ||            \
                               Py_TYPE(ob) == &CDataOwning_Type)
#define CDataOwn_Check(ob)    (Py_TYPE(ob) == &CDataOwning_Type)

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

typedef struct {
    ffi_cif cif;
    /* the following information is used when doing the call:
       - a buffer of size 'exchange_size' is malloced
       - the arguments are converted from Python objects to raw data
       - the i'th raw data is stored at 'buffer + exchange_offset_arg[1+i]'
       - the call is done
       - the result is read back from 'buffer + exchange_offset_arg[0]' */
    Py_ssize_t exchange_size;
    Py_ssize_t exchange_offset_arg[1];
} cif_description_t;

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
    ct->ct_stuff = NULL;
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
    Py_XDECREF(ct->ct_stuff);
    if (ct->ct_flags & CT_FUNCTIONPTR)
        PyObject_Free(ct->ct_extra);
    Py_TYPE(ct)->tp_free((PyObject *)ct);
}

static int
ctypedescr_traverse(CTypeDescrObject *ct, visitproc visit, void *arg)
{
    Py_VISIT(ct->ct_itemdescr);
    Py_VISIT(ct->ct_stuff);
    return 0;
}

static int
ctypedescr_clear(CTypeDescrObject *ct)
{
    Py_CLEAR(ct->ct_itemdescr);
    Py_CLEAR(ct->ct_stuff);
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

static char *
get_field_name(CTypeDescrObject *ct, CFieldObject *cf)
{
    Py_ssize_t i = 0;
    PyObject *d_key, *d_value;
    while (PyDict_Next(ct->ct_stuff, &i, &d_key, &d_value)) {
        if (d_value == (PyObject *)cf)
            return PyString_AsString(d_key);
    }
    return NULL;
}

static void
cfield_dealloc(CFieldObject *cf)
{
    Py_DECREF(cf->cf_type);
    PyObject_Del(cf);
}

static int
cfield_traverse(CFieldObject *cf, visitproc visit, void *arg)
{
    Py_VISIT(cf->cf_type);
    return 0;
}

#undef OFF
#define OFF(x) offsetof(CFieldObject, x)

static PyMemberDef cfield_members[] = {
    {"type", T_OBJECT, OFF(cf_type), RO},
    {"offset", T_PYSSIZET, OFF(cf_offset), RO},
    {"bitsize", T_INT, OFF(cf_bitsize), RO},
    {NULL}      /* Sentinel */
};
#undef OFF

static PyTypeObject CField_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.CField",
    sizeof(CFieldObject),
    0,
    (destructor)cfield_dealloc,                 /* tp_dealloc */
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
    Py_TPFLAGS_DEFAULT,                         /* tp_flags */
    0,                                          /* tp_doc */
    (traverseproc)cfield_traverse,              /* tp_traverse */
    0,                                          /* tp_clear */
    0,                                          /* tp_richcompare */
    0,                                          /* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    0,                                          /* tp_methods */
    cfield_members,                             /* tp_members */
};

/************************************************************/

static unsigned PY_LONG_LONG
_my_PyLong_AsUnsignedLongLong(PyObject *ob, int overflow)
{
    /* (possibly) convert and cast a Python object to an unsigned long long.
       Like PyLong_AsLongLong(), this version accepts a Python int too,
       does convertions from other types of objects.  If 'overflow',
       complains with OverflowError; if '!overflow', mask the result. */
    if (PyInt_Check(ob)) {
        long value1 = PyInt_AS_LONG(ob);
        if (overflow && value1 < 0)
            goto negative;
        return (unsigned PY_LONG_LONG)(PY_LONG_LONG)value1;
    }
    else if (PyLong_Check(ob)) {
        if (overflow) {
            if (_PyLong_Sign(ob) < 0)
                goto negative;
            return PyLong_AsUnsignedLongLong(ob);
        }
        else {
            return PyLong_AsUnsignedLongLongMask(ob);
        }
    }
    else {
        PyObject *io;
        unsigned PY_LONG_LONG res;
        PyNumberMethods *nb = ob->ob_type->tp_as_number;

        if (nb == NULL || nb->nb_int == NULL) {
            PyErr_SetString(PyExc_TypeError, "an integer is required");
            return (unsigned PY_LONG_LONG)-1;
        }
        io = (*nb->nb_int) (ob);
        if (io == NULL)
            return (unsigned PY_LONG_LONG)-1;

        if (!PyInt_Check(io) && !PyLong_Check(io)) {
            Py_DECREF(io);
            PyErr_SetString(PyExc_TypeError, "integer conversion failed");
            return -1;
        }
        res = _my_PyLong_AsUnsignedLongLong(io, overflow);
        Py_DECREF(io);
        return res;
    }

 negative:
    PyErr_SetString(PyExc_OverflowError,
                    "can't convert negative number to unsigned");
    return -1;
}

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

static double
read_raw_float_data(char *target, int size)
{
    if (size == sizeof(float))
        return *((float*)target);
    else if (size == sizeof(double))
        return *((double*)target);
    else {
        Py_FatalError("read_raw_float_data: bad float size");
        return 0;
    }
}

static void
write_raw_float_data(char *target, double source, int size)
{
    if (size == sizeof(float))
        *((float*)target) = source;
    else if (size == sizeof(double))
        *((double*)target) = source;
    else
        Py_FatalError("write_raw_float_data: bad float size");
}

static PyObject *
new_simple_cdata(char *data, CTypeDescrObject *ct)
{
    CDataObject *cd = PyObject_New(CDataObject, &CData_Type);
    if (cd == NULL)
        return NULL;
    Py_INCREF(ct);
    cd->c_data = data;
    cd->c_type = ct;
    return (PyObject *)cd;
}

static PyObject *
convert_to_object(char *data, CTypeDescrObject *ct)
{
    if (!(ct->ct_flags & CT_PRIMITIVE_ANY)) {
        /* non-primitive types (check done just for performance) */
        if (ct->ct_flags & CT_POINTER) {
            char *ptrdata = *(char **)data;
            if (ptrdata != NULL) {
                return new_simple_cdata(ptrdata, ct);
            }
            else {
                Py_INCREF(Py_None);
                return Py_None;
            }
        }
        else if (ct->ct_flags & CT_OPAQUE) {
            PyErr_Format(PyExc_TypeError, "cannot return a cdata '%s'",
                         ct->ct_name);
            return NULL;
        }
        else if (ct->ct_flags & (CT_ARRAY|CT_STRUCT|CT_UNION)) {
            return new_simple_cdata(data, ct);
        }
    }
    else if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        PY_LONG_LONG value = read_raw_signed_data(data, ct->ct_size);

        if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
            return PyInt_FromLong((long)value);
        else
            return PyLong_FromLongLong(value);
    }
    else if (ct->ct_flags & CT_PRIMITIVE_UNSIGNED) {
        unsigned PY_LONG_LONG value =read_raw_unsigned_data(data, ct->ct_size);

        if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
            return PyInt_FromLong((long)value);
        else
            return PyLong_FromUnsignedLongLong(value);
    }
    else if (ct->ct_flags & CT_PRIMITIVE_FLOAT) {
        double value = read_raw_float_data(data, ct->ct_size);
        return PyFloat_FromDouble(value);
    }
    else if (ct->ct_flags & CT_PRIMITIVE_CHAR) {
        return PyString_FromStringAndSize(data, 1);
    }

    fprintf(stderr, "convert_to_object: '%s'\n", ct->ct_name);
    Py_FatalError("convert_to_object");
    return NULL;
}

static int
convert_from_object(char *data, CTypeDescrObject *ct, PyObject *init)
{
    PyObject *s;
    const char *expected;

    if (ct->ct_flags & CT_ARRAY) {
        CTypeDescrObject *ctitem = ct->ct_itemdescr;

        if (PyList_Check(init) || PyTuple_Check(init)) {
            PyObject **items;
            Py_ssize_t i, n;
            n = PySequence_Fast_GET_SIZE(init);
            if (ct->ct_length >= 0 && n > ct->ct_length) {
                PyErr_Format(PyExc_IndexError,
                             "too many initializers for '%s' (got %zd)",
                             ct->ct_name, n);
                return -1;
            }
            items = PySequence_Fast_ITEMS(init);
            for (i=0; i<n; i++) {
                if (convert_from_object(data, ctitem, items[i]) < 0)
                    return -1;
                data += ctitem->ct_size;
            }
            return 0;
        }
        else if (ctitem->ct_flags & CT_PRIMITIVE_CHAR) {
            char *srcdata;
            Py_ssize_t n;
            if (!PyString_Check(init)) {
                expected = "str or list or tuple";
                goto cannot_convert;
            }
            n = PyString_GET_SIZE(init);
            if (ct->ct_length >= 0 && n > ct->ct_length) {
                PyErr_Format(PyExc_IndexError,
                             "initializer string is too long for '%s' "
                             "(got %zd characters)", ct->ct_name, n);
                return -1;
            }
            srcdata = PyString_AS_STRING(init);
            memcpy(data, srcdata, n);
            return 0;
        }
        else {
            expected = "list or tuple";
            goto cannot_convert;
        }
    }
    if (ct->ct_flags & CT_POINTER) {
        char *ptrdata;
        CTypeDescrObject *ctinit;

        if (init != Py_None) {
            expected = "compatible pointer";
            if (!CData_Check(init))
                goto cannot_convert;
            ctinit = ((CDataObject *)init)->c_type;
            if (ctinit->ct_itemdescr != ct->ct_itemdescr &&
                    !(ct->ct_itemdescr->ct_flags & CT_CAST_ANYTHING))
                goto cannot_convert;
            ptrdata = ((CDataObject *)init)->c_data;
        }
        else {
            ptrdata = NULL;
        }
        *(char **)data = ptrdata;
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        PY_LONG_LONG value = PyLong_AsLongLong(init);
        if (value == -1 && PyErr_Occurred())
            return -1;
        write_raw_integer_data(data, value, ct->ct_size);
        if (value != read_raw_signed_data(data, ct->ct_size))
            goto overflow;
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_UNSIGNED) {
        unsigned PY_LONG_LONG value = _my_PyLong_AsUnsignedLongLong(init, 1);
        if (value == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred())
            return -1;
        write_raw_integer_data(data, value, ct->ct_size);
        if (value != read_raw_unsigned_data(data, ct->ct_size))
            goto overflow;
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_FLOAT) {
        double value = PyFloat_AsDouble(init);
        write_raw_float_data(data, value, ct->ct_size);
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_CHAR) {
        if (PyString_Check(init) && PyString_GET_SIZE(init) == 1) {
            data[0] = PyString_AS_STRING(init)[0];
            return 0;
        }
        if (CData_Check(init) &&
               (((CDataObject *)init)->c_type->ct_flags & CT_PRIMITIVE_CHAR)) {
            data[0] = ((CDataObject *)init)->c_data[0];
            return 0;
        }
        expected = "string of length 1";
        goto cannot_convert;
    }
    if (ct->ct_flags & CT_STRUCT) {

        if (CData_Check(init)) {
            if (((CDataObject *)init)->c_type == ct && ct->ct_size >= 0) {
                memcpy(data, ((CDataObject *)init)->c_data, ct->ct_size);
                return 0;
            }
        }
        if (PyList_Check(init) || PyTuple_Check(init)) {
            PyObject **items = PySequence_Fast_ITEMS(init);
            Py_ssize_t i, n = PySequence_Fast_GET_SIZE(init);
            CFieldObject *cf = (CFieldObject *)ct->ct_extra;

            for (i=0; i<n; i++) {
                if (cf == NULL) {
                    PyErr_Format(PyExc_ValueError,
                                 "too many initializers for '%s' (got %zd)",
                                 ct->ct_name, n);
                    return -1;
                }
                if (convert_from_object(data + cf->cf_offset,
                                        cf->cf_type, items[i]) < 0)
                    return -1;
                cf = cf->cf_next;
            }
            return 0;
        }
        if (PyDict_Check(init)) {
            PyObject *d_key, *d_value;
            Py_ssize_t i = 0;
            CFieldObject *cf;

            while (PyDict_Next(init, &i, &d_key, &d_value)) {
                cf = (CFieldObject *)PyDict_GetItem(ct->ct_stuff, d_key);
                if (cf == NULL) {
                    PyErr_SetObject(PyExc_KeyError, d_key);
                    return -1;
                }
                if (convert_from_object(data + cf->cf_offset,
                                        cf->cf_type, d_value) < 0)
                    return -1;
            }
            return 0;
        }
        expected = "list or tuple or dict or struct-cdata";
        goto cannot_convert;
    }
    if (ct->ct_flags & CT_UNION) {
        CFieldObject *cf = (CFieldObject *)ct->ct_extra;   /* first field */
        if (cf == NULL) {
            PyErr_SetString(PyExc_ValueError, "empty union");
            return -1;
        }
        return convert_from_object(data, cf->cf_type, init);
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

 cannot_convert:
    if (CData_Check(init))
        PyErr_Format(PyExc_TypeError,
                     "initializer for ctype '%s' must be a %s, "
                     "not cdata '%s'",
                     ct->ct_name, expected,
                     ((CDataObject *)init)->c_type->ct_name);
    else
        PyErr_Format(PyExc_TypeError,
                     "initializer for ctype '%s' must be a %s, "
                     "not %.200s",
                     ct->ct_name, expected, Py_TYPE(init)->tp_name);
    return -1;
}

static Py_ssize_t
get_array_length(CDataObject *cd)
{
    if (cd->c_type->ct_length < 0)
        return ((CDataObject_with_length *)cd)->length;
    else
        return cd->c_type->ct_length;
}

static int
get_alignment(CTypeDescrObject *ct)
{
    int align;
 retry:
    if (ct->ct_flags & (CT_PRIMITIVE_ANY|CT_STRUCT|CT_UNION)) {
        align = ct->ct_length;
    }
    else if (ct->ct_flags & CT_POINTER) {
        struct aligncheck_ptr { char x; char *y; };
        align = offsetof(struct aligncheck_ptr, y);
    }
    else if (ct->ct_flags & CT_ARRAY) {
        ct = ct->ct_itemdescr;
        goto retry;
    }
    else {
        PyErr_Format(PyExc_TypeError, "ctype '%s' is of unknown alignment",
                     ct->ct_name);
        return -1;
    }

    if ((align < 1) || (align & (align-1))) {
        PyErr_Format(PyExc_TypeError,
                     "found for ctype '%s' bogus alignment '%d'",
                     ct->ct_name, align);
        return -1;
    }
    return align;
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

static PyObject *cdata_str(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_CHAR) {
        return PyString_FromStringAndSize(cd->c_data, 1);
    }
    else if (cd->c_type->ct_itemdescr != NULL &&
             cd->c_type->ct_itemdescr->ct_flags & CT_PRIMITIVE_CHAR) {
        Py_ssize_t length;

        if (cd->c_type->ct_flags & CT_ARRAY)
            length = strnlen(cd->c_data, get_array_length(cd));
        else
            length = strlen(cd->c_data);

        return PyString_FromStringAndSize(cd->c_data, length);
    }
    else
        return cdata_repr(cd);
}

static PyObject *cdataowning_repr(CDataObject *cd)
{
    Py_ssize_t size;
    if (cd->c_type->ct_flags & CT_POINTER)
        size = cd->c_type->ct_itemdescr->ct_size;
    else if (cd->c_type->ct_flags & CT_ARRAY)
        size = get_array_length(cd) * cd->c_type->ct_itemdescr->ct_size;
    else
        size = cd->c_type->ct_size;

    return PyString_FromFormat("<cdata '%s' owning %zd bytes>",
                               cd->c_type->ct_name, size);
}

static int cdata_nonzero(CDataObject *cd)
{
    return cd->c_data != NULL;
}

static PyObject *cdata_int(CDataObject *cd)
{
    if (cd->c_type->ct_flags & (CT_PRIMITIVE_SIGNED|CT_PRIMITIVE_UNSIGNED)) {
        return convert_to_object(cd->c_data, cd->c_type);
    }
    else if (cd->c_type->ct_flags & CT_PRIMITIVE_CHAR) {
        return PyInt_FromLong((unsigned char)cd->c_data[0]);
    }
    else if (cd->c_type->ct_flags & CT_PRIMITIVE_FLOAT) {
        PyObject *o = convert_to_object(cd->c_data, cd->c_type);
        PyObject *r = o ? PyNumber_Int(o) : NULL;
        Py_XDECREF(o);
        return r;
    }
    PyErr_Format(PyExc_TypeError, "int() not supported on cdata '%s'",
                 cd->c_type->ct_name);
    return NULL;
}

static PyObject *cdata_long(CDataObject *cd)
{
    PyObject *res = cdata_int(cd);
    if (res != NULL && PyInt_CheckExact(res)) {
        PyObject *o = PyLong_FromLong(PyInt_AS_LONG(res));
        Py_DECREF(res);
        res = o;
    }
    return res;
}

static PyObject *cdata_float(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_FLOAT) {
        return convert_to_object(cd->c_data, cd->c_type);
    }
    PyErr_Format(PyExc_TypeError, "float() not supported on cdata '%s'",
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
    equal = (obv->c_type == obw->c_type) && (obv->c_data == obw->c_data);
    return (equal ^ (op == Py_NE)) ? Py_True : Py_False;

 Unimplemented:
    Py_INCREF(Py_NotImplemented);
    return Py_NotImplemented;
}

static long cdata_hash(CDataObject *cd)
{
    long h = _Py_HashPointer(cd->c_type) ^ _Py_HashPointer(cd->c_data);
    if (h == -1)
        h = -2;
    return h;
}

static Py_ssize_t
cdata_length(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_ARRAY) {
        return get_array_length(cd);
    }
    PyErr_Format(PyExc_TypeError, "cdata of type '%s' has no len()",
                 cd->c_type->ct_name);
    return -1;
}

static PyObject *
cdata_subscript(CDataObject *cd, PyObject *key)
{
    CTypeDescrObject *ctitem = cd->c_type->ct_itemdescr;
    /* use 'mp_subscript' instead of 'sq_item' because we don't want
       negative indexes to be corrected automatically */
    Py_ssize_t i = PyNumber_AsSsize_t(key, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred())
        return NULL;

    if (cd->c_type->ct_flags & CT_POINTER) {
        if (CDataOwn_Check(cd) && i != 0) {
            PyErr_Format(PyExc_IndexError,
                         "cdata '%s' can only be indexed by 0",
                         cd->c_type->ct_name);
            return NULL;
        }
    }
    else if (cd->c_type->ct_flags & CT_ARRAY) {
        if (i < 0) {
            PyErr_SetString(PyExc_IndexError,
                            "negative index not supported");
            return NULL;
        }
        if (i >= get_array_length(cd)) {
            PyErr_Format(PyExc_IndexError,
                         "index too large for cdata '%s' (expected %zd < %zd)",
                         cd->c_type->ct_name,
                         i, get_array_length(cd));
            return NULL;
        }
    }
    else {
        PyErr_Format(PyExc_TypeError, "cdata of type '%s' cannot be indexed",
                     cd->c_type->ct_name);
        return NULL;
    }
    return convert_to_object(cd->c_data + i * ctitem->ct_size, ctitem);
}

static int
cdata_ass_sub(CDataObject *cd, PyObject *key, PyObject *v)
{
    CTypeDescrObject *ctitem = cd->c_type->ct_itemdescr;
    /* use 'mp_ass_subscript' instead of 'sq_ass_item' because we don't want
       negative indexes to be corrected automatically */
    Py_ssize_t i = PyNumber_AsSsize_t(key, PyExc_IndexError);
    if (i == -1 && PyErr_Occurred())
        return -1;

    if (cd->c_type->ct_flags & CT_POINTER) {
        if (CDataOwn_Check(cd) && i != 0) {
            PyErr_Format(PyExc_IndexError,
                         "cdata '%s' can only be indexed by 0",
                         cd->c_type->ct_name);
            return -1;
        }
    }
    else if (cd->c_type->ct_flags & CT_ARRAY) {
        if (i < 0) {
            PyErr_SetString(PyExc_IndexError,
                            "negative index not supported");
            return -1;
        }
        if (i >= get_array_length(cd)) {
            PyErr_Format(PyExc_IndexError,
                         "index too large for cdata '%s' (expected %zd < %zd)",
                         cd->c_type->ct_name,
                         i, get_array_length(cd));
            return -1;
        }
    }
    else {
        PyErr_Format(PyExc_TypeError,
                     "cdata of type '%s' does not support index assignment",
                     cd->c_type->ct_name);
        return -1;
    }
    return convert_from_object(cd->c_data + i * ctitem->ct_size, ctitem, v);
}

static PyObject *
_cdata_add_or_sub(PyObject *v, PyObject *w, int sign)
{
    Py_ssize_t i;
    CDataObject *cd;
    CTypeDescrObject *ctptr;

    if (!CData_Check(v))
        goto not_implemented;

    i = PyNumber_AsSsize_t(w, PyExc_OverflowError);
    if (i == -1 && PyErr_Occurred())
        return NULL;
    i *= sign;

    cd = (CDataObject *)v;
    if (cd->c_type->ct_flags & CT_POINTER)
        ctptr = cd->c_type;
    else if (cd->c_type->ct_flags & CT_ARRAY) {
        ctptr = (CTypeDescrObject *)cd->c_type->ct_stuff;
    }
    else {
        PyErr_Format(PyExc_TypeError, "cannot add a cdata '%s' and a number",
                     cd->c_type->ct_name);
        return NULL;
    }
    if (ctptr->ct_itemdescr->ct_size < 0) {
        PyErr_Format(PyExc_TypeError,
                     "ctype '%s' points to items of unknown size",
                     cd->c_type->ct_name);
        return NULL;
    }
    return new_simple_cdata(cd->c_data + i * ctptr->ct_itemdescr->ct_size,
                            ctptr);

 not_implemented:
    Py_INCREF(Py_NotImplemented);               \
    return Py_NotImplemented;                   \
}

static PyObject *
cdata_add(PyObject *v, PyObject *w)
{
    return _cdata_add_or_sub(v, w, +1);
}

static PyObject *
cdata_sub(PyObject *v, PyObject *w)
{
    if (CData_Check(v) && CData_Check(w)) {
        CDataObject *cdv = (CDataObject *)v;
        CDataObject *cdw = (CDataObject *)w;
        CTypeDescrObject *ct = cdw->c_type;
        Py_ssize_t diff;

        if (ct->ct_flags & CT_ARRAY)     /* ptr_to_T - array_of_T: ok */
            ct = (CTypeDescrObject *)ct->ct_stuff;

        if (ct != cdv->c_type || !(ct->ct_flags & CT_POINTER) ||
                (ct->ct_itemdescr->ct_size <= 0)) {
            PyErr_Format(PyExc_TypeError,
                         "cannot subtract cdata '%s' and cdata '%s'",
                         ct->ct_name, cdw->c_type->ct_name);
            return NULL;
        }
        diff = (cdv->c_data - cdw->c_data) / ct->ct_itemdescr->ct_size;
        return PyInt_FromSsize_t(diff);
    }

    return _cdata_add_or_sub(v, w, -1);
}

static PyObject *
cdata_getattro(CDataObject *cd, PyObject *attr)
{
    CFieldObject *cf;
    CTypeDescrObject *ct = cd->c_type;

    if (ct->ct_flags & CT_POINTER)
        ct = ct->ct_itemdescr;

    if ((ct->ct_flags & (CT_STRUCT|CT_UNION)) && ct->ct_stuff != NULL) {
        cf = (CFieldObject *)PyDict_GetItem(ct->ct_stuff, attr);
        if (cf != NULL) {
            /* read the field 'cf' */
            char *data = cd->c_data + cf->cf_offset;
            return convert_to_object(data, cf->cf_type);
        }
    }
    return PyObject_GenericGetAttr((PyObject *)cd, attr);
}

static int
cdata_setattro(CDataObject *cd, PyObject *attr, PyObject *value)
{
    CFieldObject *cf;
    CTypeDescrObject *ct = cd->c_type;

    if (ct->ct_flags & CT_POINTER)
        ct = ct->ct_itemdescr;

    if ((ct->ct_flags & (CT_STRUCT|CT_UNION)) && ct->ct_stuff != NULL) {
        cf = (CFieldObject *)PyDict_GetItem(ct->ct_stuff, attr);
        if (cf != NULL) {
            /* write the field 'cf' */
            char *data = cd->c_data + cf->cf_offset;
            if (value != NULL) {
                return convert_from_object(data, cf->cf_type, value);
            }
            else {
                PyErr_SetString(PyExc_AttributeError,
                                "cannot delete struct field");
                return -1;
            }
        }
    }
    return PyObject_GenericSetAttr((PyObject *)cd, attr, value);
}

static PyObject*
cdata_call(CDataObject *cd, PyObject *args, PyObject *kwds)
{
    char *buffer;
    void** buffer_array;
    cif_description_t *cif_descr;
    Py_ssize_t i, nargs;
    PyObject *signature, *res;
    CTypeDescrObject *restype;
    char *resultdata;

    if (!(cd->c_type->ct_flags & CT_FUNCTIONPTR)) {
        PyErr_Format(PyExc_TypeError, "cdata '%s' is not callable",
                     cd->c_type->ct_name);
        return NULL;
    }
    if (kwds != NULL && PyDict_Size(kwds) != 0) {
        PyErr_SetString(PyExc_TypeError,
                "a cdata function cannot be called with keyword arguments");
        return NULL;
    }
    signature = cd->c_type->ct_stuff;
    nargs = PyTuple_GET_SIZE(signature) - 1;
    if (PyTuple_Size(args) != nargs) {
        if (!PyErr_Occurred()) {
            PyObject *s = cdata_repr(cd);
            PyErr_Format(PyExc_TypeError,
                         "%s expects %zd arguments, got %zd",
                         PyString_AsString(s),
                         nargs, PyTuple_GET_SIZE(args));
        }
        return NULL;
    }

    cif_descr = (cif_description_t *)cd->c_type->ct_extra;
    buffer = PyObject_Malloc(cif_descr->exchange_size);
    if (buffer == NULL)
        return PyErr_NoMemory();

    buffer_array = (void **)buffer;

    for (i=0; i<nargs; i++) {
        CTypeDescrObject *argtype;
        char *data = buffer + cif_descr->exchange_offset_arg[1 + i];
        argtype = (CTypeDescrObject *)PyTuple_GET_ITEM(signature, 1 + i);
        buffer_array[i] = data;
        if (convert_from_object(data, argtype, PyTuple_GET_ITEM(args, i)) < 0)
            return NULL;
    }

    restype = (CTypeDescrObject *)PyTuple_GET_ITEM(signature, 0);
    resultdata = buffer + cif_descr->exchange_offset_arg[0];

    ffi_call(&cif_descr->cif, (void (*)(void))(cd->c_data),
             resultdata, buffer_array);

    if (restype->ct_flags & CT_VOID) {
        res = Py_None;
        Py_INCREF(res);
    }
    else {
        res = convert_to_object(resultdata, (CTypeDescrObject *)restype);
    }
    PyObject_Free(buffer);
    return res;
}

static PyNumberMethods CData_as_number = {
    (binaryfunc)cdata_add,      /*nb_add*/
    (binaryfunc)cdata_sub,      /*nb_subtract*/
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
    (unaryfunc)cdata_long,      /*nb_long*/
    (unaryfunc)cdata_float,     /*nb_float*/
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
    (ternaryfunc)cdata_call,                    /* tp_call */
    (reprfunc)cdata_str,                        /* tp_str */
    (getattrofunc)cdata_getattro,               /* tp_getattro */
    (setattrofunc)cdata_setattro,               /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_CHECKTYPES, /* tp_flags */
    0,                                          /* tp_doc */
    (traverseproc)cdata_traverse,               /* tp_traverse */
    0,                                          /* tp_clear */
    cdata_richcompare,                          /* tp_richcompare */
};

static PyTypeObject CDataOwning_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_ffi_backend.CDataOwn",
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
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_CHECKTYPES, /* tp_flags */
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
    Py_ssize_t dataoffset, datasize, explicitlength;
    if (!PyArg_ParseTuple(args, "O!O:new", &CTypeDescr_Type, &ct, &init))
        return NULL;

    explicitlength = -1;
    if (ct->ct_flags & CT_POINTER) {
        dataoffset = offsetof(CDataObject_with_alignment, alignment);
        ctitem = ct->ct_itemdescr;
        datasize = ctitem->ct_size;
        if (datasize < 0) {
            PyErr_Format(PyExc_TypeError,
                         "cannot instantiate ctype '%s' of unknown size",
                         ctitem->ct_name);
            return NULL;
        }
        if (ctitem->ct_flags & CT_PRIMITIVE_CHAR)
            datasize += sizeof(char);  /* forcefully add a null character */
    }
    else if (ct->ct_flags & CT_ARRAY) {
        dataoffset = offsetof(CDataObject_with_alignment, alignment);
        datasize = ct->ct_size;
        if (datasize < 0) {
            if (PyList_Check(init) || PyTuple_Check(init)) {
                explicitlength = PySequence_Fast_GET_SIZE(init);
            }
            else if (PyString_Check(init)) {
                /* from a string, we add the null terminator */
                explicitlength = PyString_GET_SIZE(init) + 1;
            }
            else {
                explicitlength = PyNumber_AsSsize_t(init, PyExc_OverflowError);
                if (explicitlength < 0) {
                    if (!PyErr_Occurred())
                        PyErr_SetString(PyExc_ValueError,
                                        "negative array length");
                    return NULL;
                }
                init = Py_None;
            }
            ctitem = ct->ct_itemdescr;
            dataoffset = offsetof(CDataObject_with_length, alignment);
            datasize = explicitlength * ctitem->ct_size;
            if (explicitlength > 0 &&
                    (datasize / explicitlength) != ctitem->ct_size) {
                PyErr_SetString(PyExc_OverflowError,
                                "array size would overflow a Py_ssize_t");
                return NULL;
            }
        }
    }
    else {
        PyErr_SetString(PyExc_TypeError, "expected a pointer or array ctype");
        return NULL;
    }

    cd = (CDataObject *)PyObject_Malloc(dataoffset + datasize);
    if (PyObject_Init((PyObject *)cd, &CDataOwning_Type) == NULL)
        return NULL;

    Py_INCREF(ct);
    cd->c_type = ct;
    cd->c_data = ((char *)cd) + dataoffset;
    if (explicitlength >= 0)
        ((CDataObject_with_length*)cd)->length = explicitlength;

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

static CDataObject *_new_casted_primitive(CTypeDescrObject *ct)
{
    int dataoffset = offsetof(CDataObject_with_alignment, alignment);
    CDataObject *cd = (CDataObject *)PyObject_Malloc(dataoffset + ct->ct_size);
    if (PyObject_Init((PyObject *)cd, &CData_Type) == NULL)
        return NULL;
    Py_INCREF(ct);
    cd->c_type = ct;
    cd->c_data = ((char*)cd) + dataoffset;
    return cd;
}

static PyObject *b_cast(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    CDataObject *cd;
    PyObject *ob;
    if (!PyArg_ParseTuple(args, "O!O:cast", &CTypeDescr_Type, &ct, &ob))
        return NULL;

    if (ct->ct_flags & (CT_POINTER|CT_FUNCTIONPTR)) {
        /* cast to a pointer or to a funcptr */
        unsigned PY_LONG_LONG value;

        if (CData_Check(ob)) {
            CDataObject *cdsrc = (CDataObject *)ob;
            if (cdsrc->c_type->ct_flags & (CT_POINTER|CT_ARRAY)) {
                return new_simple_cdata(cdsrc->c_data, ct);
            }
        }
        value = _my_PyLong_AsUnsignedLongLong(ob, 0);
        if (value == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred())
            return NULL;
        return new_simple_cdata((char *)(Py_intptr_t)value, ct);
    }
    else if (ct->ct_flags & (CT_PRIMITIVE_SIGNED|CT_PRIMITIVE_UNSIGNED
                             |CT_PRIMITIVE_CHAR)) {
        /* cast to an integer type or a char */
        unsigned PY_LONG_LONG value;

        if (CData_Check(ob) &&
               ((CDataObject *)ob)->c_type->ct_flags & (CT_POINTER|CT_ARRAY)) {
            value = (Py_intptr_t)((CDataObject *)ob)->c_data;
        }
        else if (PyString_Check(ob)) {
            if (PyString_GET_SIZE(ob) != 1)
                goto cannot_cast;
            value = (unsigned char)PyString_AS_STRING(ob)[0];
        }
        else {
            value = _my_PyLong_AsUnsignedLongLong(ob, 0);
            if (value == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred())
                return NULL;
        }
        cd = _new_casted_primitive(ct);
        if (cd != NULL)
            write_raw_integer_data(cd->c_data, value, ct->ct_size);
        return (PyObject *)cd;
    }
    else if (ct->ct_flags & CT_PRIMITIVE_FLOAT) {
        /* cast to a float */
        double value;
        PyObject *io;

        if (CData_Check(ob)) {
            CDataObject *cdsrc = (CDataObject *)ob;

            if (!(cdsrc->c_type->ct_flags & CT_PRIMITIVE_ANY))
                goto cannot_cast;
            io = convert_to_object(cdsrc->c_data, cdsrc->c_type);
            if (io == NULL)
                return NULL;
        }
        else {
            io = ob;
            Py_INCREF(io);
        }

        if (PyString_Check(io)) {
            if (PyString_GET_SIZE(io) != 1) {
                Py_DECREF(io);
                goto cannot_cast;
            }
            value = (unsigned char)PyString_AS_STRING(io)[0];
        }
        else {
            value = PyFloat_AsDouble(io);
        }
        Py_DECREF(io);
        if (value == -1.0 && PyErr_Occurred())
            return NULL;

        cd = _new_casted_primitive(ct);
        if (cd != NULL)
            write_raw_float_data(cd->c_data, value, ct->ct_size);
        return (PyObject *)cd;
    }
    else
        goto cannot_cast;

 cannot_cast:
    if (CData_Check(ob))
        PyErr_Format(PyExc_TypeError, "cannot cast ctype '%s' to ctype '%s'",
                     ((CDataObject *)ob)->c_type->ct_name, ct->ct_name);
    else
        PyErr_Format(PyExc_TypeError,
                     "cannot cast %.200s object to ctype '%s'",
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
#define ENUM_PRIMITIVE_TYPES                                    \
       EPTYPE(c, char, CT_PRIMITIVE_CHAR | CT_CAST_ANYTHING)    \
       EPTYPE(s, short, CT_PRIMITIVE_SIGNED )                   \
       EPTYPE(i, int, CT_PRIMITIVE_SIGNED )                     \
       EPTYPE(l, long, CT_PRIMITIVE_SIGNED )                    \
       EPTYPE(ll, long long, CT_PRIMITIVE_SIGNED )              \
       EPTYPE(sc, signed char, CT_PRIMITIVE_SIGNED )            \
       EPTYPE(uc, unsigned char, CT_PRIMITIVE_UNSIGNED )        \
       EPTYPE(us, unsigned short, CT_PRIMITIVE_UNSIGNED )       \
       EPTYPE(ui, unsigned int, CT_PRIMITIVE_UNSIGNED )         \
       EPTYPE(ul, unsigned long, CT_PRIMITIVE_UNSIGNED )        \
       EPTYPE(ull, unsigned long long, CT_PRIMITIVE_UNSIGNED )  \
       EPTYPE(f, float, CT_PRIMITIVE_FLOAT )                    \
       EPTYPE(d, double, CT_PRIMITIVE_FLOAT )

#define EPTYPE(code, typename, flags)                   \
    struct aligncheck_##code { char x; typename y; };
    ENUM_PRIMITIVE_TYPES
#undef EPTYPE

    CTypeDescrObject *td;
    const char *name;
    static const struct descr_s { const char *name; int size, align, flags; }
    types[] = {
#define EPTYPE(code, typename, flags)                   \
        { #typename,                                    \
          sizeof(typename),                             \
          offsetof(struct aligncheck_##code, y),        \
          flags                                         \
        },
    ENUM_PRIMITIVE_TYPES
#undef EPTYPE
#undef ENUM_PRIMITIVE_TYPES
        { NULL }
    };
    const struct descr_s *ptypes;
    int name_size;
    ffi_type *ffitype;

    if (!PyArg_ParseTuple(args, "s:new_primitive_type", &name))
        return NULL;

    for (ptypes=types; ; ptypes++) {
        if (ptypes->name == NULL) {
            PyErr_SetString(PyExc_KeyError, name);
            return NULL;
        }
        if (strcmp(name, ptypes->name) == 0)
            break;
    }

    if (ptypes->flags & CT_PRIMITIVE_SIGNED) {
        switch (ptypes->size) {
        case 1: ffitype = &ffi_type_sint8; break;
        case 2: ffitype = &ffi_type_sint16; break;
        case 4: ffitype = &ffi_type_sint32; break;
        case 8: ffitype = &ffi_type_sint64; break;
        default: goto bad_ffi_type;
        }
    }
    else if (ptypes->flags & CT_PRIMITIVE_FLOAT) {
        if (strcmp(ptypes->name, "float") == 0)
            ffitype = &ffi_type_float;
        else if (strcmp(ptypes->name, "double") == 0)
            ffitype = &ffi_type_double;
        else
            goto bad_ffi_type;
    }
    else {
        switch (ptypes->size) {
        case 1: ffitype = &ffi_type_uint8; break;
        case 2: ffitype = &ffi_type_uint16; break;
        case 4: ffitype = &ffi_type_uint32; break;
        case 8: ffitype = &ffi_type_uint64; break;
        default: goto bad_ffi_type;
        }
    }

    name_size = strlen(ptypes->name) + 1;
    td = ctypedescr_new(name_size);
    if (td == NULL)
        return NULL;

    memcpy(td->ct_name, name, name_size);
    td->ct_size = ptypes->size;
    td->ct_length = ptypes->align;
    td->ct_extra = ffitype;
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

 bad_ffi_type:
    PyErr_Format(PyExc_NotImplementedError,
                 "primitive type '%s' with a non-standard size %d",
                 name, ptypes->size);
    return NULL;
}

static PyObject *b_new_pointer_type(PyObject *self, PyObject *args)
{
    CTypeDescrObject *td, *ctitem;

    if (!PyArg_ParseTuple(args, "O!:new_pointer_type",
                          &CTypeDescr_Type, &ctitem))
        return NULL;

    td = ctypedescr_new_on_top(ctitem, " *", 2);
    if (td == NULL)
        return NULL;

    td->ct_size = sizeof(void *);
    td->ct_flags = CT_POINTER;
    return (PyObject *)td;
}

static PyObject *b_new_array_type(PyObject *self, PyObject *args)
{
    PyObject *lengthobj;
    CTypeDescrObject *td, *ctitem, *ctptr;
    char extra_text[32];
    Py_ssize_t length, arraysize;

    if (!PyArg_ParseTuple(args, "O!O:new_array_type",
                          &CTypeDescr_Type, &ctptr, &lengthobj))
        return NULL;

    if (!(ctptr->ct_flags & CT_POINTER)) {
        PyErr_SetString(PyExc_TypeError, "first arg must be a pointer ctype");
        return NULL;
    }
    ctitem = ctptr->ct_itemdescr;
    if (ctitem->ct_size < 0) {
        PyErr_Format(PyExc_ValueError, "array item of unknown size: '%s'",
                     ctitem->ct_name);
        return NULL;
    }

    if (lengthobj == Py_None) {
        sprintf(extra_text, "[]");
        length = -1;
        arraysize = -1;
    }
    else {
        length = PyNumber_AsSsize_t(lengthobj, PyExc_OverflowError);
        if (length < 0) {
            if (!PyErr_Occurred())
                PyErr_SetString(PyExc_ValueError, "negative array length");
            return NULL;
        }
        sprintf(extra_text, "[%zd]", length);
        arraysize = length * ctitem->ct_size;
        if (length > 0 && (arraysize / length) != ctitem->ct_size) {
            PyErr_SetString(PyExc_OverflowError,
                            "array size would overflow a Py_ssize_t");
            return NULL;
        }
    }
    td = ctypedescr_new_on_top(ctitem, extra_text, 0);
    if (td == NULL)
        return NULL;

    Py_INCREF(ctptr);
    td->ct_stuff = (PyObject *)ctptr;
    td->ct_size = arraysize;
    td->ct_length = length;
    td->ct_flags = CT_ARRAY;
    return (PyObject *)td;
}

static PyObject *b_new_void_type(PyObject *self, PyObject *args)
{
    int name_size = strlen("void") + 1;
    CTypeDescrObject *td = ctypedescr_new(name_size);
    if (td == NULL)
        return NULL;

    memcpy(td->ct_name, "void", name_size);
    td->ct_size = -1;
    td->ct_flags = CT_VOID | CT_OPAQUE | CT_CAST_ANYTHING;
    td->ct_name_position = strlen("void");
    return (PyObject *)td;
}

static PyObject *_b_struct_or_union_type(const char *kind, const char *name,
                                         int flag)
{
    int kindlen = strlen(kind);
    int namelen = strlen(name);
    CTypeDescrObject *td = ctypedescr_new(kindlen + 1 + namelen + 1);
    if (td == NULL)
        return NULL;

    td->ct_size = -1;
    td->ct_flags = flag | CT_OPAQUE;
    memcpy(td->ct_name, kind, kindlen);
    td->ct_name[kindlen] = ' ';
    memcpy(td->ct_name + kindlen + 1, name, namelen + 1);
    td->ct_name_position = kindlen + 1 + namelen;
    return (PyObject *)td;
}

static PyObject *b_new_struct_type(PyObject *self, PyObject *args)
{
    char *name;
    if (!PyArg_ParseTuple(args, "s:new_struct_type", &name))
        return NULL;
    return _b_struct_or_union_type("struct", name, CT_STRUCT);
}

static PyObject *b_new_union_type(PyObject *self, PyObject *args)
{
    char *name;
    if (!PyArg_ParseTuple(args, "s:new_union_type", &name))
        return NULL;
    return _b_struct_or_union_type("union", name, CT_UNION);
}

static PyObject *b_complete_struct_or_union(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    PyObject *fields, *interned_fields;
    int is_union, alignment;
    Py_ssize_t offset, i, nb_fields, maxsize;
    CFieldObject **previous;

    if (!PyArg_ParseTuple(args, "O!O!:complete_struct_or_union",
                          &CTypeDescr_Type, &ct,
                          &PyList_Type, &fields))
        return NULL;

    if ((ct->ct_flags & (CT_STRUCT|CT_OPAQUE)) == (CT_STRUCT|CT_OPAQUE)) {
        is_union = 0;
    }
    else if ((ct->ct_flags & (CT_UNION|CT_OPAQUE)) == (CT_UNION|CT_OPAQUE)) {
        is_union = 1;
    }
    else {
        PyErr_SetString(PyExc_TypeError,
                  "first arg must be a non-initialized struct or union ctype");
        return NULL;
    }

    maxsize = 1;
    alignment = 1;
    offset = 0;
    nb_fields = PyList_GET_SIZE(fields);
    interned_fields = PyDict_New();
    if (interned_fields == NULL)
        return NULL;

    previous = (CFieldObject **)&ct->ct_extra;

    for (i=0; i<nb_fields; i++) {
        PyObject *fname;
        CTypeDescrObject *ftype;
        int fbitsize, falign, err;
        CFieldObject *cf;

        if (!PyArg_ParseTuple(PyList_GET_ITEM(fields, i), "O!O!i:list item",
                              &PyString_Type, &fname,
                              &CTypeDescr_Type, &ftype,
                              &fbitsize))
            goto error;

        if (ftype->ct_size < 0) {
            PyErr_Format(PyExc_TypeError,
                         "field '%s' has ctype '%s' of unknown size",
                         PyString_AS_STRING(fname),
                         ftype->ct_name);
            goto error;
        }

        falign = get_alignment(ftype);
        if (falign < 0)
            goto error;
        if (alignment < falign)
            alignment = falign;

        /* align this field to its own 'falign' by inserting padding */
        offset = (offset + falign - 1) & ~(falign-1);

        cf = PyObject_New(CFieldObject, &CField_Type);
        if (cf == NULL)
            goto error;
        Py_INCREF(ftype);
        cf->cf_type = ftype;
        cf->cf_offset = offset;
        cf->cf_bitsize = fbitsize;

        if (fbitsize >= 0) {
            Py_DECREF(cf);
            PyErr_SetString(PyExc_NotImplementedError, "bit fields");
            goto error;
        }

        Py_INCREF(fname);
        PyString_InternInPlace(&fname);
        err = PyDict_SetItem(interned_fields, fname, (PyObject *)cf);
        Py_DECREF(fname);
        Py_DECREF(cf);
        if (err < 0)
            goto error;

        if (PyDict_Size(interned_fields) != i + 1) {
            PyErr_Format(PyExc_KeyError, "duplicate field name '%s'",
                         PyString_AS_STRING(fname));
            goto error;
        }

        *previous = cf;
        previous = &cf->cf_next;

        if (maxsize < ftype->ct_size)
            maxsize = ftype->ct_size;
        if (!is_union)
            offset += ftype->ct_size;
    }
    *previous = NULL;

    if (is_union) {
        assert(offset == 0);
        ct->ct_size = maxsize;
    }
    else {
        if (offset == 0)
            offset = 1;
        offset = (offset + alignment - 1) & ~(alignment-1);
        ct->ct_size = offset;
    }
    ct->ct_length = alignment;
    ct->ct_stuff = interned_fields;
    ct->ct_flags &= ~CT_OPAQUE;

    Py_INCREF(Py_None);
    return Py_None;

 error:
    Py_DECREF(interned_fields);
    return NULL;
}

static PyObject *b__getfields(PyObject *self, PyObject *arg)
{
    CTypeDescrObject *ct = (CTypeDescrObject *)arg;
    PyObject *d, *res;

    if (!CTypeDescr_Check(arg) ||
            !(ct->ct_flags & (CT_STRUCT|CT_UNION))) {
        PyErr_SetString(PyExc_TypeError, "expected a 'ctype' struct or union");
        return NULL;
    }
    d = (PyObject *)ct->ct_stuff;
    if (d == NULL) {
        res = Py_None;
        Py_INCREF(res);
    }
    else {
        CFieldObject *cf;
        res = PyList_New(0);
        if (res == NULL)
            return NULL;
        for (cf = (CFieldObject *)ct->ct_extra; cf != NULL; cf = cf->cf_next) {
            int err;
            PyObject *o = Py_BuildValue("sO", get_field_name(ct, cf),
                                        (PyObject *)cf);
            err = (o != NULL) ? PyList_Append(res, o) : -1;
            Py_XDECREF(o);
            if (err < 0) {
                Py_DECREF(res);
                return NULL;
            }
        }
    }
    return res;
}

struct funcbuilder_s {
    Py_ssize_t nb_bytes;
    Py_ssize_t nb_bytes_in_name;
    char *bufferp, *namep;
    ffi_type **atypes;
    ffi_type *rtype;
    unsigned int nargs;
    int name_position;
};

static void *fb_alloc(struct funcbuilder_s *fb, Py_ssize_t size)
{
    if (fb->bufferp == NULL) {
        fb->nb_bytes += size;
        return NULL;
    }
    else {
        char *result = fb->bufferp;
        fb->bufferp += size;
        return result;
    }
}

static void fb_cat_name(struct funcbuilder_s *fb, char *piece, int piecelen)
{
    if (fb->namep == NULL) {
        fb->nb_bytes_in_name += piecelen;
    }
    else {
        memcpy(fb->namep, piece, piecelen);
        fb->namep += piecelen;
    }
}

static ffi_type *fb_fill_type(struct funcbuilder_s *fb, CTypeDescrObject *ct)
{
    if (ct->ct_flags & CT_PRIMITIVE_ANY) {
        return (ffi_type *)ct->ct_extra;
    }
    else if (ct->ct_flags & (CT_POINTER|CT_ARRAY|CT_FUNCTIONPTR)) {
        return &ffi_type_pointer;
    }
    else if (ct->ct_flags & CT_VOID) {
        return &ffi_type_void;
    }

    if (ct->ct_size < 0) {
        PyErr_Format(PyExc_TypeError, "ctype '%s' has incomplete type",
                     ct->ct_name);
        return NULL;
    }
    if (ct->ct_flags & CT_STRUCT) {
        ffi_type *ffistruct, *ffifield;
        ffi_type **elements;
        Py_ssize_t i, n;
        CFieldObject *cf;

        n = PyDict_Size(ct->ct_stuff);
        elements = fb_alloc(fb, (n + 1) * sizeof(ffi_type*));
        cf = (CFieldObject *)ct->ct_extra;

        for (i=0; i<n; i++) {
            assert(cf != NULL);
            ffifield = fb_fill_type(fb, cf->cf_type);
            if (elements != NULL)
                elements[i] = ffifield;
            cf = cf->cf_next;
        }
        assert(cf == NULL);

        ffistruct = fb_alloc(fb, sizeof(ffi_type));
        if (ffistruct != NULL) {
            elements[n] = NULL;
            ffistruct->size = ct->ct_size;
            ffistruct->alignment = ct->ct_length;
            ffistruct->type = FFI_TYPE_STRUCT;
            ffistruct->elements = elements;
        }
        return ffistruct;
    }
    else {
        PyErr_Format(PyExc_NotImplementedError,
                     "ctype '%s' not supported as argument or return value",
                     ct->ct_name);
        return NULL;
    }
}

#define ALIGN_ARG(n)  ((n) + 7) & ~7

static int fb_build(struct funcbuilder_s *fb, PyObject *fargs,
                    CTypeDescrObject *fresult)
{
    Py_ssize_t i, nargs = PyTuple_GET_SIZE(fargs);
    Py_ssize_t exchange_offset;
    cif_description_t *cif_descr;

    /* ffi buffer: start with a cif_description */
    cif_descr = fb_alloc(fb, sizeof(cif_description_t) +
                             nargs * sizeof(Py_ssize_t));

    /* ffi buffer: next comes an array of 'ffi_type*', one per argument */
    fb->nargs = nargs;
    fb->atypes = fb_alloc(fb, nargs * sizeof(ffi_type*));

    /* ffi buffer: next comes the result type */
    fb->rtype = fb_fill_type(fb, fresult);
    if (PyErr_Occurred())
        return -1;
    if (cif_descr != NULL) {
        if (fb->rtype->type == FFI_TYPE_STRUCT) {
            PyErr_SetString(PyExc_NotImplementedError,
                            "functions returning structs are not supported");
            return -1;
        }
        /* exchange data size */
        /* first, enough room for an array of 'nargs' pointers */
        exchange_offset = nargs * sizeof(void*);
        exchange_offset = ALIGN_ARG(exchange_offset);
        cif_descr->exchange_offset_arg[0] = exchange_offset;
        /* then enough room for the result --- which means at least
           sizeof(ffi_arg), according to the ffi docs */
        i = fb->rtype->size;
        if (i < sizeof(ffi_arg))
            i = sizeof(ffi_arg);
        exchange_offset += i;
    }

    /* name: the function type name we build here is, like in C, made
       as follows:

         RESULT_TYPE_HEAD (*)(ARG_1_TYPE, ARG_2_TYPE, etc) RESULT_TYPE_TAIL
    */
    fb_cat_name(fb, fresult->ct_name, fresult->ct_name_position);
    fb_cat_name(fb, "(*)(", 4);
    i = fresult->ct_name_position + 2;  /* between '(*' and ')(' */
    fb->name_position = i;

    /* loop over the arguments */
    for (i=0; i<nargs; i++) {
        CTypeDescrObject *farg;
        ffi_type *atype;

        farg = (CTypeDescrObject *)PyTuple_GET_ITEM(fargs, i);
        if (!CTypeDescr_Check(farg)) {
            PyErr_SetString(PyExc_TypeError, "expected a tuple of ctypes");
            return -1;
        }

        /* ffi buffer: fill in the ffi for the i'th argument */
        atype = fb_fill_type(fb, farg);
        if (PyErr_Occurred())
            return -1;
        if (fb->atypes != NULL) {
            fb->atypes[i] = atype;
            /* exchange data size */
            exchange_offset = ALIGN_ARG(exchange_offset);
            cif_descr->exchange_offset_arg[1 + i] = exchange_offset;
            exchange_offset += atype->size;
        }

        /* name: concatenate the name of the i'th argument's type */
        if (i > 0)
            fb_cat_name(fb, ", ", 2);
        fb_cat_name(fb, farg->ct_name, strlen(farg->ct_name));
    }

    if (cif_descr != NULL) {
        /* exchange data size */
        cif_descr->exchange_size = exchange_offset;
    }

    /* name: concatenate the tail of the result type */
    fb_cat_name(fb, ")", 1);
    fb_cat_name(fb, fresult->ct_name + fresult->ct_name_position,
                strlen(fresult->ct_name) - fresult->ct_name_position + 1);
    return 0;
}

#undef ALIGN_ARG

static PyObject *b_new_function_type(PyObject *self, PyObject *args)
{
    PyObject *fargs;
    CTypeDescrObject *fresult;
    CTypeDescrObject *fct;
    int ellipsis;
    struct funcbuilder_s funcbuilder;
    char *buffer;
    cif_description_t *cif_descr;
    Py_ssize_t i;

    if (!PyArg_ParseTuple(args, "O!O!i:new_function_type",
                          &PyTuple_Type, &fargs,
                          &CTypeDescr_Type, &fresult,
                          &ellipsis))
        return NULL;

    if (ellipsis) {
        PyErr_SetString(PyExc_NotImplementedError, "'...'");
        return NULL;
    }

    funcbuilder.nb_bytes = 0;
    funcbuilder.nb_bytes_in_name = 0;
    funcbuilder.bufferp = NULL;
    funcbuilder.namep = NULL;

    /* compute the total size needed in the buffer for libffi */
    if (fb_build(&funcbuilder, fargs, fresult) < 0)
        return NULL;

    /* allocate the buffer */
    buffer = PyObject_Malloc(funcbuilder.nb_bytes);
    if (buffer == NULL)
        return PyErr_NoMemory();

    /* allocate the function type */
    fct = ctypedescr_new(funcbuilder.nb_bytes_in_name);
    if (fct == NULL)
        goto error;

    /* call again fb_build() to really build the libffi data structures
       and the ct_name */
    funcbuilder.bufferp = buffer;
    funcbuilder.namep = fct->ct_name;
    if (fb_build(&funcbuilder, fargs, fresult) < 0)
        goto error;
    assert(funcbuilder.bufferp == buffer + funcbuilder.nb_bytes);
    assert(funcbuilder.namep == fct->ct_name + funcbuilder.nb_bytes_in_name);

    cif_descr = (cif_description_t *)buffer;
    if (ffi_prep_cif(&cif_descr->cif, FFI_DEFAULT_ABI, funcbuilder.nargs,
                     funcbuilder.rtype, funcbuilder.atypes) != FFI_OK) {
        PyErr_SetString(PyExc_SystemError,
                        "libffi fails to build this function type");
        goto error;
    }

    /* build the signature, given by a tuple of ctype objects */
    fct->ct_stuff = PyTuple_New(1 + funcbuilder.nargs);
    if (fct->ct_stuff == NULL)
        goto error;
    Py_INCREF(fresult);
    PyTuple_SET_ITEM(fct->ct_stuff, 0, (PyObject *)fresult);
    for (i=0; i<funcbuilder.nargs; i++) {
        PyObject *o = PyTuple_GET_ITEM(fargs, i);
        /* convert arrays into pointers */
        if (((CTypeDescrObject *)o)->ct_flags & CT_ARRAY)
            o = ((CTypeDescrObject *)o)->ct_stuff;
        Py_INCREF(o);
        PyTuple_SET_ITEM(fct->ct_stuff, 1 + i, o);
    }
    fct->ct_extra = buffer;
    fct->ct_size = sizeof(void(*)(void));
    fct->ct_flags = CT_FUNCTIONPTR;
    fct->ct_name_position = funcbuilder.name_position;
    return (PyObject *)fct;

 error:
    Py_XDECREF(fct);
    PyObject_Free(buffer);
    return NULL;
}

static PyObject *b_alignof(PyObject *self, PyObject *arg)
{
    int align;
    if (!CTypeDescr_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected a 'ctype' object");
        return NULL;
    }
    align = get_alignment((CTypeDescrObject *)arg);
    if (align < 0)
        return NULL;
    return PyInt_FromLong(align);
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
    return PyInt_FromSsize_t(((CTypeDescrObject *)arg)->ct_size);
}

static PyObject *b_sizeof_instance(PyObject *self, PyObject *arg)
{
    CDataObject *cd;
    Py_ssize_t size;

    if (!CData_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected a 'cdata' object");
        return NULL;
    }
    cd = (CDataObject *)arg;

    if (cd->c_type->ct_flags & CT_ARRAY)
        size = get_array_length(cd) * cd->c_type->ct_itemdescr->ct_size;
    else
        size = cd->c_type->ct_size;

    return PyInt_FromSsize_t(size);
}

static PyObject *b_typeof_instance(PyObject *self, PyObject *arg)
{
    PyObject *res;

    if (!CData_Check(arg)) {
        PyErr_SetString(PyExc_TypeError, "expected a 'cdata' object");
        return NULL;
    }
    res = (PyObject *)((CDataObject *)arg)->c_type;
    Py_INCREF(res);
    return res;
}

static PyObject *b_offsetof(PyObject *self, PyObject *args)
{
    PyObject *fieldname;
    CTypeDescrObject *ct;
    CFieldObject *cf;

    if (!PyArg_ParseTuple(args, "O!O:offsetof",
                          &CTypeDescr_Type, &ct, &fieldname))
        return NULL;

    if (!((ct->ct_flags & (CT_STRUCT|CT_UNION)) && ct->ct_stuff != NULL)) {
        PyErr_SetString(PyExc_TypeError,
                        "not an initialized struct or union ctype");
        return NULL;
    }
    cf = (CFieldObject *)PyDict_GetItem(ct->ct_stuff, fieldname);
    if (cf == NULL) {
        PyErr_SetObject(PyExc_KeyError, fieldname);
        return NULL;
    }
    return PyInt_FromSsize_t(cf->cf_offset);
}

static PyObject *b_string(PyObject *self, PyObject *args)
{
    CDataObject *cd;
    CTypeDescrObject *ct;
    Py_ssize_t length;
    if (!PyArg_ParseTuple(args, "O!n:string",
                          &CData_Type, &cd, &length))
        return NULL;
    ct = cd->c_type;
    if (!(ct->ct_flags & CT_POINTER) ||
            !(ct->ct_itemdescr->ct_flags & CT_CAST_ANYTHING)) {
        PyErr_Format(PyExc_TypeError,
                     "expected a cdata 'char *' or 'void *', got '%s'",
                     ct->ct_name);
        return NULL;
    }
    return PyString_FromStringAndSize(cd->c_data, length);
}

/************************************************************/

static char _testfunc0(char a, char b)
{
    return a + b;
}
static long _testfunc1(int a, long b)
{
    return (long)a + b;
}
static PY_LONG_LONG _testfunc2(PY_LONG_LONG a, PY_LONG_LONG b)
{
    return a + b;
}
static double _testfunc3(float a, double b)
{
    return a + b;
}
static float _testfunc4(float a, double b)
{
    return a + b;
}
static void _testfunc5(void)
{
}
static int *_testfunc6(int *x)
{
    static int y;
    y = *x - 1000;
    return &y;
}
struct _testfunc7_s { char a1; short a2; };
static short _testfunc7(struct _testfunc7_s inlined)
{
    return inlined.a1 + inlined.a2;
}

static PyObject *b__testfunc(PyObject *self, PyObject *args)
{
    /* for testing only */
    int i;
    void *f;
    if (!PyArg_ParseTuple(args, "i:_testfunc", &i))
        return NULL;
    switch (i) {
    case 0: f = &_testfunc0; break;
    case 1: f = &_testfunc1; break;
    case 2: f = &_testfunc2; break;
    case 3: f = &_testfunc3; break;
    case 4: f = &_testfunc4; break;
    case 5: f = &_testfunc5; break;
    case 6: f = &_testfunc6; break;
    case 7: f = &_testfunc7; break;
    default:
        PyErr_SetNone(PyExc_ValueError);
        return NULL;
    }
    return PyLong_FromVoidPtr(f);
}

static PyMethodDef FFIBackendMethods[] = {
    {"nonstandard_integer_types", b_nonstandard_integer_types, METH_NOARGS},
    {"load_library", b_load_library, METH_VARARGS},
    {"new_primitive_type", b_new_primitive_type, METH_VARARGS},
    {"new_pointer_type", b_new_pointer_type, METH_VARARGS},
    {"new_array_type", b_new_array_type, METH_VARARGS},
    {"new_void_type", b_new_void_type, METH_NOARGS},
    {"new_struct_type", b_new_struct_type, METH_VARARGS},
    {"new_union_type", b_new_union_type, METH_VARARGS},
    {"complete_struct_or_union", b_complete_struct_or_union, METH_VARARGS},
    {"new_function_type", b_new_function_type, METH_VARARGS},
    {"_getfields", b__getfields, METH_O},
    {"new", b_new, METH_VARARGS},
    {"cast", b_cast, METH_VARARGS},
    {"alignof", b_alignof, METH_O},
    {"sizeof_type", b_sizeof_type, METH_O},
    {"sizeof_instance", b_sizeof_instance, METH_O},
    {"typeof_instance", b_typeof_instance, METH_O},
    {"offsetof", b_offsetof, METH_VARARGS},
    {"string", b_string, METH_VARARGS},
    {"_testfunc", b__testfunc, METH_VARARGS},
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
    if (PyType_Ready(&CField_Type) < 0)
        return;
    if (PyType_Ready(&CData_Type) < 0)
        return;
    if (PyType_Ready(&CDataOwning_Type) < 0)
        return;
}
