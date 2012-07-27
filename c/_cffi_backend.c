#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "structmember.h"

#ifdef MS_WIN32
#include <windows.h>
#include "misc_win32.h"
#else
#include <stddef.h>
#include <stdint.h>
#include <dlfcn.h>
#include <errno.h>
#include <ffi.h>
#include <sys/mman.h>
#endif

#include "malloc_closure.h"

/* Define USE__THREAD if gcc on your platform supports "__thread"
   global variables. */
#if !defined(MS_WIN32) && !defined(X86_DARWIN) && !defined(POWERPC_DARWIN)
# define USE__THREAD
#endif

/************************************************************/

/* base type flag: exactly one of the following: */
#define CT_PRIMITIVE_SIGNED   1    /* signed integer */
#define CT_PRIMITIVE_UNSIGNED 2    /* unsigned integer */
#define CT_PRIMITIVE_CHAR     4    /* char, wchar_t */
#define CT_PRIMITIVE_FLOAT    8    /* float, double */
#define CT_POINTER           16    /* pointer, excluding ptr-to-func */
#define CT_ARRAY             32    /* array */
#define CT_STRUCT            64    /* struct */
#define CT_UNION            128    /* union */
#define CT_FUNCTIONPTR      256    /* pointer to function */
#define CT_VOID             512    /* void */

/* other flags that may also be set in addition to the base flag: */
#define CT_CAST_ANYTHING         1024    /* 'char *' and 'void *' only */
#define CT_PRIMITIVE_FITS_LONG   2048
#define CT_IS_OPAQUE             4096
#define CT_IS_ENUM               8192
#define CT_IS_PTR_TO_OWNED      16384
#define CT_CUSTOM_FIELD_POS     32768
#define CT_PRIMITIVE_ANY  (CT_PRIMITIVE_SIGNED |        \
                           CT_PRIMITIVE_UNSIGNED |      \
                           CT_PRIMITIVE_CHAR |          \
                           CT_PRIMITIVE_FLOAT)

typedef struct _ctypedescr {
    PyObject_VAR_HEAD

    struct _ctypedescr *ct_itemdescr;  /* ptrs and arrays: the item type */
    PyObject *ct_stuff;                /* structs: dict of the fields
                                          arrays: ctypedescr of the ptr type
                                          function: tuple(abi, ctres, ctargs..)
                                          enum: pair {"name":x},{x:"name"} */
    void *ct_extra;                    /* structs: first field (not a ref!)
                                          function types: cif_description
                                          primitives: prebuilt "cif" object */

    PyObject *ct_weakreflist;    /* weakref support */

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
    short cf_bitshift, cf_bitsize;
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
} CDataObject_casted_primitive;

typedef struct {
    CDataObject head;
    PyObject *weakreflist;
} CDataObject_own_base;

typedef struct {
    CDataObject_own_base head;
    union_alignment alignment;
} CDataObject_own_nolength;

typedef struct {
    CDataObject_own_base head;
    Py_ssize_t length;
    union_alignment alignment;
} CDataObject_own_length;

typedef struct {
    CDataObject_own_base head;
    PyObject *structobj;
} CDataObject_own_structptr;

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


/* whenever running Python code, the errno is saved in this thread-local
   variable */
#ifndef MS_WIN32
# ifdef USE__THREAD
static __thread int cffi_saved_errno = 0;
static void save_errno(void) { cffi_saved_errno = errno; }
static void restore_errno(void) { errno = cffi_saved_errno; }
static void init_errno(void) { }
# else
#  include "misc_thread.h"
# endif
#endif

#ifdef HAVE_WCHAR_H
# include "wchar_helper.h"
#endif

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
    ct->ct_weakreflist = NULL;
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
    if (ct->ct_weakreflist != NULL)
        PyObject_ClearWeakRefs((PyObject *) ct);
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
    "_cffi_backend.CTypeDescr",
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
    0,                                          /* tp_richcompare */
    offsetof(CTypeDescrObject, ct_weakreflist), /* tp_weaklistoffset */
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
    {"bitshift", T_SHORT, OFF(cf_bitshift), RO},
    {"bitsize", T_SHORT, OFF(cf_bitsize), RO},
    {NULL}      /* Sentinel */
};
#undef OFF

static PyTypeObject CField_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_cffi_backend.CField",
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

static PY_LONG_LONG
_my_PyLong_AsLongLong(PyObject *ob)
{
    /* (possibly) convert and cast a Python object to a long long.
       Like PyLong_AsLongLong(), this version accepts a Python int too, and
       does convertions from other types of objects.  The difference is that
       this version refuses floats. */
    if (PyInt_Check(ob)) {
        return PyInt_AS_LONG(ob);
    }
    else if (PyLong_Check(ob)) {
        return PyLong_AsLongLong(ob);
    }
    else {
        PyObject *io;
        PY_LONG_LONG res;
        PyNumberMethods *nb = ob->ob_type->tp_as_number;

        if (PyFloat_Check(ob) ||
                nb == NULL || nb->nb_int == NULL) {
            PyErr_SetString(PyExc_TypeError, "an integer is required");
            return -1;
        }
        io = (*nb->nb_int) (ob);
        if (io == NULL)
            return -1;

        if (PyInt_Check(io) || PyLong_Check(io)) {
            res = _my_PyLong_AsLongLong(io);
        }
        else {
            PyErr_SetString(PyExc_TypeError, "integer conversion failed");
            res = -1;
        }
        Py_DECREF(io);
        return res;
    }
}

static unsigned PY_LONG_LONG
_my_PyLong_AsUnsignedLongLong(PyObject *ob, int strict)
{
    /* (possibly) convert and cast a Python object to an unsigned long long.
       Like PyLong_AsLongLong(), this version accepts a Python int too, and
       does convertions from other types of objects.  If 'strict', complains
       with OverflowError and refuses floats.  If '!strict', rounds floats
       and masks the result. */
    if (PyInt_Check(ob)) {
        long value1 = PyInt_AS_LONG(ob);
        if (strict && value1 < 0)
            goto negative;
        return (unsigned PY_LONG_LONG)(PY_LONG_LONG)value1;
    }
    else if (PyLong_Check(ob)) {
        if (strict) {
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

        if ((strict && PyFloat_Check(ob)) ||
                nb == NULL || nb->nb_int == NULL) {
            PyErr_SetString(PyExc_TypeError, "an integer is required");
            return (unsigned PY_LONG_LONG)-1;
        }
        io = (*nb->nb_int) (ob);
        if (io == NULL)
            return (unsigned PY_LONG_LONG)-1;

        if (PyInt_Check(io) || PyLong_Check(io)) {
            res = _my_PyLong_AsUnsignedLongLong(io, strict);
        }
        else {
            PyErr_SetString(PyExc_TypeError, "integer conversion failed");
            res = (unsigned PY_LONG_LONG)-1;
        }
        Py_DECREF(io);
        return res;
    }

 negative:
    PyErr_SetString(PyExc_OverflowError,
                    "can't convert negative number to unsigned");
    return (unsigned PY_LONG_LONG)-1;
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
        *((unsigned char*)target) = (unsigned char)source;
    else if (size == sizeof(unsigned short))
        *((unsigned short*)target) = (unsigned short)source;
    else if (size == sizeof(unsigned int))
        *((unsigned int*)target) = (unsigned int)source;
    else if (size == sizeof(unsigned long))
        *((unsigned long*)target) = (unsigned long)source;
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
        *((float*)target) = (float)source;
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

static PyObject *convert_enum_string_to_int(CTypeDescrObject *ct, PyObject *ob)
{
    PyObject *d_value;

    if (PyString_AS_STRING(ob)[0] == '#') {
        char *number = PyString_AS_STRING(ob) + 1;   /* strip initial '#' */
        PyObject *ob2 = PyString_FromString(number);
        if (ob2 == NULL)
            return NULL;

        d_value = PyNumber_Long(ob2);
        Py_DECREF(ob2);
    }
    else {
        d_value = PyDict_GetItem(PyTuple_GET_ITEM(ct->ct_stuff, 0), ob);
        if (d_value == NULL) {
            PyErr_Format(PyExc_ValueError,
                         "'%s' is not an enumerator for %s",
                         PyString_AS_STRING(ob),
                         ct->ct_name);
            return NULL;
        }
        Py_INCREF(d_value);
    }
    return d_value;
}

static PyObject *
convert_to_object(char *data, CTypeDescrObject *ct)
{
    if (!(ct->ct_flags & CT_PRIMITIVE_ANY)) {
        /* non-primitive types (check done just for performance) */
        if (ct->ct_flags & (CT_POINTER|CT_FUNCTIONPTR)) {
            char *ptrdata = *(char **)data;
            return new_simple_cdata(ptrdata, ct);
        }
        else if (ct->ct_flags & CT_IS_OPAQUE) {
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

        if (ct->ct_flags & CT_IS_ENUM) {
            PyObject *d_value, *d_key = PyInt_FromLong((int)value);
            if (d_key == NULL)
                return NULL;

            d_value = PyDict_GetItem(PyTuple_GET_ITEM(ct->ct_stuff, 1), d_key);
            Py_DECREF(d_key);
            if (d_value != NULL)
                Py_INCREF(d_value);
            else
                d_value = PyString_FromFormat("#%d", (int)value);
            return d_value;
        }
        else if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
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
        if (ct->ct_size == sizeof(char))
            return PyString_FromStringAndSize(data, 1);
#ifdef HAVE_WCHAR_H
        else
            return _my_PyUnicode_FromWideChar((wchar_t *)data, 1);
#endif
    }

    PyErr_Format(PyExc_SystemError,
                 "convert_to_object: '%s'", ct->ct_name);
    return NULL;
}

static PyObject *
convert_to_object_bitfield(char *data, CFieldObject *cf)
{
    CTypeDescrObject *ct = cf->cf_type;

    if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        unsigned PY_LONG_LONG value, valuemask, shiftforsign;
        PY_LONG_LONG result;

        value = (unsigned PY_LONG_LONG)read_raw_signed_data(data, ct->ct_size);
        valuemask = (1ULL << cf->cf_bitsize) - 1ULL;
        shiftforsign = 1ULL << (cf->cf_bitsize - 1);
        value = ((value >> cf->cf_bitshift) + shiftforsign) & valuemask;
        result = ((PY_LONG_LONG)value) - (PY_LONG_LONG)shiftforsign;

        if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
            return PyInt_FromLong((long)result);
        else
            return PyLong_FromLongLong(result);
    }
    else {
        unsigned PY_LONG_LONG value, valuemask;

        value = read_raw_unsigned_data(data, ct->ct_size);
        valuemask = (1ULL << cf->cf_bitsize) - 1ULL;
        value = (value >> cf->cf_bitshift) & valuemask;

        if (ct->ct_flags & CT_PRIMITIVE_FITS_LONG)
            return PyInt_FromLong((long)value);
        else
            return PyLong_FromUnsignedLongLong(value);
    }
}

static int _convert_overflow(PyObject *init, const char *ct_name)
{
    PyObject *s;
    if (PyErr_Occurred())   /* already an exception pending */
        return -1;
    s = PyObject_Str(init);
    if (s == NULL)
        return -1;
    PyErr_Format(PyExc_OverflowError, "integer %s does not fit '%s'",
                 PyString_AS_STRING(s), ct_name);
    Py_DECREF(s);
    return -1;
}

static int _convert_to_char(PyObject *init)
{
    if (PyString_Check(init) && PyString_GET_SIZE(init) == 1) {
        return (unsigned char)(PyString_AS_STRING(init)[0]);
    }
    if (CData_Check(init) &&
           (((CDataObject *)init)->c_type->ct_flags & CT_PRIMITIVE_CHAR) &&
           (((CDataObject *)init)->c_type->ct_size == sizeof(char))) {
        return *(unsigned char *)((CDataObject *)init)->c_data;
    }
    PyErr_Format(PyExc_TypeError,
                 "initializer for ctype 'char' must be a string of length 1, "
                 "not %.200s", Py_TYPE(init)->tp_name);
    return -1;
}

#ifdef HAVE_WCHAR_H
static wchar_t _convert_to_wchar_t(PyObject *init)
{
    if (PyUnicode_Check(init)) {
        wchar_t ordinal;
        if (_my_PyUnicode_AsSingleWideChar(init, &ordinal) == 0)
            return ordinal;
    }
    if (CData_Check(init) &&
           (((CDataObject *)init)->c_type->ct_flags & CT_PRIMITIVE_CHAR) &&
           (((CDataObject *)init)->c_type->ct_size == sizeof(wchar_t))) {
        return *(wchar_t *)((CDataObject *)init)->c_data;
    }
    PyErr_Format(PyExc_TypeError,
                 "initializer for ctype 'wchar_t' must be a unicode string "
                 "of length 1, not %.200s", Py_TYPE(init)->tp_name);
    return (wchar_t)-1;
}
#endif

static int _convert_error(PyObject *init, const char *ct_name,
                          const char *expected)
{
    if (CData_Check(init))
        PyErr_Format(PyExc_TypeError,
                     "initializer for ctype '%s' must be a %s, "
                     "not cdata '%s'",
                     ct_name, expected,
                     ((CDataObject *)init)->c_type->ct_name);
    else
        PyErr_Format(PyExc_TypeError,
                     "initializer for ctype '%s' must be a %s, "
                     "not %.200s",
                     ct_name, expected, Py_TYPE(init)->tp_name);
    return -1;
}

static int    /* forward */
convert_from_object(char *data, CTypeDescrObject *ct, PyObject *init);
static int    /* forward */
convert_from_object_bitfield(char *data, CFieldObject *cf, PyObject *init);

static int
convert_field_from_object(char *data, CFieldObject *cf, PyObject *value)
{
    if (cf->cf_bitshift >= 0)
        return convert_from_object_bitfield(data, cf, value);
    else
        return convert_from_object(data, cf->cf_type, value);
}

static int
convert_from_object(char *data, CTypeDescrObject *ct, PyObject *init)
{
    const char *expected;
    char buf[sizeof(PY_LONG_LONG)];

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
            if (ctitem->ct_size == sizeof(char)) {
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
                if (n != ct->ct_length)
                    n++;
                srcdata = PyString_AS_STRING(init);
                memcpy(data, srcdata, n);
                return 0;
            }
#ifdef HAVE_WCHAR_H
            else {
                Py_ssize_t n;
                if (!PyUnicode_Check(init)) {
                    expected = "unicode or list or tuple";
                    goto cannot_convert;
                }
                n = _my_PyUnicode_SizeAsWideChar(init);
                if (ct->ct_length >= 0 && n > ct->ct_length) {
                    PyErr_Format(PyExc_IndexError,
                                 "initializer unicode is too long for '%s' "
                                 "(got %zd characters)", ct->ct_name, n);
                    return -1;
                }
                if (n != ct->ct_length)
                    n++;
                _my_PyUnicode_AsWideChar(init, (wchar_t *)data, n);
                return 0;
            }
#endif
        }
        else {
            expected = "list or tuple";
            goto cannot_convert;
        }
    }
    if (ct->ct_flags & (CT_POINTER|CT_FUNCTIONPTR)) {
        char *ptrdata;
        CTypeDescrObject *ctinit;

        if (!CData_Check(init)) {
            expected = "cdata pointer";
            goto cannot_convert;
        }
        ctinit = ((CDataObject *)init)->c_type;
        if (!(ctinit->ct_flags & (CT_POINTER|CT_FUNCTIONPTR))) {
            if (ctinit->ct_flags & CT_ARRAY)
                ctinit = (CTypeDescrObject *)ctinit->ct_stuff;
            else {
                expected = "pointer or array";
                goto cannot_convert;
            }
        }
        if (ctinit != ct) {
            if ((ct->ct_flags & CT_CAST_ANYTHING) ||
                (ctinit->ct_flags & CT_CAST_ANYTHING))
                ;   /* accept void* or char* as either source or target */
            else {
                expected = "pointer to same type";
                goto cannot_convert;
            }
        }
        ptrdata = ((CDataObject *)init)->c_data;

        *(char **)data = ptrdata;
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        PY_LONG_LONG value = _my_PyLong_AsLongLong(init);

        if (value == -1 && PyErr_Occurred()) {
            if (!(ct->ct_flags & CT_IS_ENUM))
                return -1;
            else {
                PyObject *ob;
                PyErr_Clear();
                if (!PyString_Check(init)) {
                    expected = "str or int";
                    goto cannot_convert;
                }

                ob = convert_enum_string_to_int(ct, init);
                if (ob == NULL)
                    return -1;
                value = PyLong_AsLongLong(ob);
                Py_DECREF(ob);
                if (value == -1 && PyErr_Occurred())
                    return -1;
            }
        }
        write_raw_integer_data(buf, value, ct->ct_size);
        if (value != read_raw_signed_data(buf, ct->ct_size))
            goto overflow;
        write_raw_integer_data(data, value, ct->ct_size);
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_UNSIGNED) {
        unsigned PY_LONG_LONG value = _my_PyLong_AsUnsignedLongLong(init, 1);
        if (value == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred())
            return -1;
        write_raw_integer_data(buf, value, ct->ct_size);
        if (value != read_raw_unsigned_data(buf, ct->ct_size))
            goto overflow;
        write_raw_integer_data(data, value, ct->ct_size);
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_FLOAT) {
        double value = PyFloat_AsDouble(init);
        if (value == -1.0 && PyErr_Occurred())
            return -1;
        write_raw_float_data(data, value, ct->ct_size);
        return 0;
    }
    if (ct->ct_flags & CT_PRIMITIVE_CHAR) {
        if (ct->ct_size == sizeof(char)) {
            int res = _convert_to_char(init);
            if (res < 0)
                return -1;
            data[0] = res;
            return 0;
        }
#ifdef HAVE_WCHAR_H
        else {
            wchar_t res = _convert_to_wchar_t(init);
            if (res == (wchar_t)-1 && PyErr_Occurred())
                return -1;
            *(wchar_t *)data = res;
            return 0;
        }
#endif
    }
    if (ct->ct_flags & (CT_STRUCT|CT_UNION)) {

        if (CData_Check(init)) {
            if (((CDataObject *)init)->c_type == ct && ct->ct_size >= 0) {
                memcpy(data, ((CDataObject *)init)->c_data, ct->ct_size);
                return 0;
            }
        }
        if (ct->ct_flags & CT_UNION) {
            Py_ssize_t n = PyObject_Size(init);
            if (n < 0)
                return -1;
            if (n > 1) {
                PyErr_Format(PyExc_ValueError,
                             "initializer for '%s': %zd items given, but "
                             "only one supported (use a dict if needed)",
                             ct->ct_name, n);
                return -1;
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
                if (convert_field_from_object(data + cf->cf_offset,
                                              cf, items[i]) < 0)
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
                if (convert_field_from_object(data + cf->cf_offset,
                                              cf, d_value) < 0)
                    return -1;
            }
            return 0;
        }
        expected = "list or tuple or dict or struct-cdata";
        goto cannot_convert;
    }
    PyErr_Format(PyExc_SystemError,
                 "convert_from_object: '%s'", ct->ct_name);
    return -1;

 overflow:
    return _convert_overflow(init, ct->ct_name);

 cannot_convert:
    return _convert_error(init, ct->ct_name, expected);
}

static int
convert_from_object_bitfield(char *data, CFieldObject *cf, PyObject *init)
{
    CTypeDescrObject *ct = cf->cf_type;
    PY_LONG_LONG fmin, fmax, value = PyLong_AsLongLong(init);
    unsigned PY_LONG_LONG rawfielddata, rawvalue, rawmask;
    if (value == -1 && PyErr_Occurred())
        return -1;

    if (ct->ct_flags & CT_PRIMITIVE_SIGNED) {
        fmin = -(1LL << (cf->cf_bitsize-1));
        fmax = (1LL << (cf->cf_bitsize-1)) - 1LL;
        if (fmax == 0)
            fmax = 1;    /* special case to let "int x:1" receive "1" */
    }
    else {
        fmin = 0LL;
        fmax = (PY_LONG_LONG)((1ULL << cf->cf_bitsize) - 1ULL);
    }
    if (value < fmin || value > fmax) {
        /* phew, PyErr_Format does not support "%lld" in Python 2.6 */
        PyObject *svalue = NULL, *sfmin = NULL, *sfmax = NULL;
        PyObject *lfmin = NULL, *lfmax = NULL;
        svalue = PyObject_Str(init);
        if (svalue == NULL) goto skip;
        lfmin = PyLong_FromLongLong(fmin);
        if (lfmin == NULL) goto skip;
        sfmin = PyObject_Str(lfmin);
        if (sfmin == NULL) goto skip;
        lfmax = PyLong_FromLongLong(fmax);
        if (lfmax == NULL) goto skip;
        sfmax = PyObject_Str(lfmax);
        if (sfmax == NULL) goto skip;
        PyErr_Format(PyExc_OverflowError,
                     "value %s outside the range allowed by the "
                     "bit field width: %s <= x <= %s",
                     PyString_AS_STRING(svalue),
                     PyString_AS_STRING(sfmin),
                     PyString_AS_STRING(sfmax));
       skip:
        Py_XDECREF(svalue);
        Py_XDECREF(sfmin);
        Py_XDECREF(sfmax);
        Py_XDECREF(lfmin);
        Py_XDECREF(lfmax);
        return -1;
    }

    rawmask = ((1ULL << cf->cf_bitsize) - 1ULL) << cf->cf_bitshift;
    rawvalue = ((unsigned PY_LONG_LONG)value) << cf->cf_bitshift;
    rawfielddata = read_raw_unsigned_data(data, ct->ct_size);
    rawfielddata = (rawfielddata & ~rawmask) | (rawvalue & rawmask);
    write_raw_integer_data(data, rawfielddata, ct->ct_size);
    return 0;
}

static Py_ssize_t
get_array_length(CDataObject *cd)
{
    if (cd->c_type->ct_length < 0)
        return ((CDataObject_own_length *)cd)->length;
    else
        return cd->c_type->ct_length;
}

static int
get_alignment(CTypeDescrObject *ct)
{
    int align;
 retry:
    if ((ct->ct_flags & (CT_PRIMITIVE_ANY|CT_STRUCT|CT_UNION)) &&
        !(ct->ct_flags & CT_IS_OPAQUE)) {
        align = ct->ct_length;
    }
    else if (ct->ct_flags & (CT_POINTER|CT_FUNCTIONPTR)) {
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
        PyErr_Format(PyExc_SystemError,
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

static void cdataowning_dealloc(CDataObject_own_base *cdb)
{
    if (cdb->weakreflist != NULL)
        PyObject_ClearWeakRefs((PyObject *) cdb);

    if (cdb->head.c_type->ct_flags & CT_IS_PTR_TO_OWNED) {
        Py_DECREF(((CDataObject_own_structptr *)cdb)->structobj);
    }
    else if (cdb->head.c_type->ct_flags & CT_FUNCTIONPTR) {
        /* a callback */
        ffi_closure *closure = (ffi_closure *)cdb->head.c_data;
        PyObject *args = (PyObject *)(closure->user_data);
        Py_XDECREF(args);
        cffi_closure_free(closure);
    }
    cdata_dealloc(&cdb->head);
}

static int cdata_traverse(CDataObject *cd, visitproc visit, void *arg)
{
    Py_VISIT(cd->c_type);
    return 0;
}

static PyObject *cdata_repr(CDataObject *cd)
{
    char *p, *extra;
    PyObject *result, *s = NULL;

    if (cd->c_type->ct_flags & CT_PRIMITIVE_ANY) {
        PyObject *o = convert_to_object(cd->c_data, cd->c_type);
        if (o == NULL)
            return NULL;
        s = PyObject_Repr(o);
        Py_DECREF(o);
        if (s == NULL)
            return NULL;
        p = PyString_AS_STRING(s);
    }
    else {
        if (cd->c_data != NULL) {
            s = PyString_FromFormat("%p", cd->c_data);
            if (s == NULL)
                return NULL;
            p = PyString_AS_STRING(s);
        }
        else
            p = "NULL";
    }
    /* it's slightly confusing to get "<cdata 'struct foo' 0x...>" because the
       struct foo is not owned.  Trying to make it clearer, write in this
       case "<cdata 'struct foo &' 0x...>". */
    if (cd->c_type->ct_flags & (CT_STRUCT|CT_UNION))
        extra = " &";
    else
        extra = "";
    result = PyString_FromFormat("<cdata '%s%s' %s>",
                                 cd->c_type->ct_name, extra, p);
    Py_XDECREF(s);
    return result;
}

static PyObject *cdata_str(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_CHAR &&
        cd->c_type->ct_size == sizeof(char)) {
        return PyString_FromStringAndSize(cd->c_data, 1);
    }
    else if (cd->c_type->ct_itemdescr != NULL &&
             cd->c_type->ct_itemdescr->ct_flags & CT_PRIMITIVE_CHAR &&
             cd->c_type->ct_itemdescr->ct_size == sizeof(char)) {
        Py_ssize_t length;

        if (cd->c_type->ct_flags & CT_ARRAY) {
            const char *start = cd->c_data;
            const char *end;
            length = get_array_length(cd);
            end = (const char *)memchr(start, 0, length);
            if (end != NULL)
                length = end - start;
        }
        else {
            if (cd->c_data == NULL) {
                PyObject *s = cdata_repr(cd);
                if (s != NULL) {
                    PyErr_Format(PyExc_RuntimeError,
                                 "cannot use str() on %s",
                                 PyString_AS_STRING(s));
                    Py_DECREF(s);
                }
                return NULL;
            }
            length = strlen(cd->c_data);
        }

        return PyString_FromStringAndSize(cd->c_data, length);
    }
    else if (cd->c_type->ct_flags & CT_IS_ENUM)
        return convert_to_object(cd->c_data, cd->c_type);
    else
        return Py_TYPE(cd)->tp_repr((PyObject *)cd);
}

#ifdef HAVE_WCHAR_H
static PyObject *cdata_unicode(CDataObject *cd)
{
    if (cd->c_type->ct_flags & CT_PRIMITIVE_CHAR &&
        cd->c_type->ct_size == sizeof(wchar_t)) {
        return _my_PyUnicode_FromWideChar((wchar_t *)cd->c_data, 1);
    }
    else if (cd->c_type->ct_itemdescr != NULL &&
             cd->c_type->ct_itemdescr->ct_flags & CT_PRIMITIVE_CHAR &&
             cd->c_type->ct_itemdescr->ct_size == sizeof(wchar_t)) {
        Py_ssize_t length;
        const wchar_t *start = (wchar_t *)cd->c_data;

        if (cd->c_type->ct_flags & CT_ARRAY) {
            const Py_ssize_t lenmax = get_array_length(cd);
            length = 0;
            while (length < lenmax && start[length])
                length++;
        }
        else {
            if (cd->c_data == NULL) {
                PyObject *s = cdata_repr(cd);
                if (s != NULL) {
                    PyErr_Format(PyExc_RuntimeError,
                                 "cannot use unicode() on %s",
                                 PyString_AS_STRING(s));
                    Py_DECREF(s);
                }
                return NULL;
            }
            length = 0;
            while (start[length])
                length++;
        }

        return _my_PyUnicode_FromWideChar((wchar_t *)cd->c_data, length);
    }
    else
        return Py_TYPE(cd)->tp_repr((PyObject *)cd);
}
#endif

static PyObject *cdataowning_repr(CDataObject *cd)
{
    Py_ssize_t size;
    if (cd->c_type->ct_flags & CT_POINTER)
        size = cd->c_type->ct_itemdescr->ct_size;
    else if (cd->c_type->ct_flags & CT_ARRAY)
        size = get_array_length(cd) * cd->c_type->ct_itemdescr->ct_size;
    else if (cd->c_type->ct_flags & CT_FUNCTIONPTR)
        goto callback_repr;
    else
        size = cd->c_type->ct_size;

    return PyString_FromFormat("<cdata '%s' owning %zd bytes>",
                               cd->c_type->ct_name, size);

 callback_repr:
    {
        PyObject *s, *res;
        PyObject *args = (PyObject *)((ffi_closure *)cd->c_data)->user_data;
        if (args == NULL)
            return cdata_repr(cd);

        s = PyObject_Repr(PyTuple_GET_ITEM(args, 1));
        if (s == NULL)
            return NULL;
        res = PyString_FromFormat("<cdata '%s' calling %s>",
                                  cd->c_type->ct_name, PyString_AsString(s));
        Py_DECREF(s);
        return res;
    }
}

static int cdata_nonzero(CDataObject *cd)
{
    return cd->c_data != NULL;
}

static PyObject *cdata_int(CDataObject *cd)
{
    if ((cd->c_type->ct_flags & (CT_PRIMITIVE_SIGNED|CT_PRIMITIVE_FITS_LONG))
                             == (CT_PRIMITIVE_SIGNED|CT_PRIMITIVE_FITS_LONG)) {
        /* this case is to handle enums, but also serves as a slight
           performance improvement for some other primitive types */
        long value = (long)read_raw_signed_data(cd->c_data,
                                                cd->c_type->ct_size);
        return PyInt_FromLong(value);
    }
    if (cd->c_type->ct_flags & (CT_PRIMITIVE_SIGNED|CT_PRIMITIVE_UNSIGNED)) {
        return convert_to_object(cd->c_data, cd->c_type);
    }
    else if (cd->c_type->ct_flags & CT_PRIMITIVE_CHAR) {
        if (cd->c_type->ct_size == sizeof(char))
            return PyInt_FromLong((unsigned char)cd->c_data[0]);
#ifdef HAVE_WCHAR_H
        else
            return PyInt_FromLong((long)*(wchar_t *)cd->c_data);
#endif
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
    int res;
    PyObject *pyres;
    char *v_cdata, *w_cdata;

    assert(CData_Check(v));
    if (!CData_Check(w))
        goto Unimplemented;

    v_cdata = ((CDataObject *)v)->c_data;
    w_cdata = ((CDataObject *)w)->c_data;
    if ((op != Py_EQ && op != Py_NE) &&
        ((((CDataObject *)v)->c_type->ct_flags & CT_PRIMITIVE_ANY) ||
         (((CDataObject *)w)->c_type->ct_flags & CT_PRIMITIVE_ANY)))
        goto Error;

    switch (op) {
    case Py_EQ: res = (v_cdata == w_cdata); break;
    case Py_NE: res = (v_cdata != w_cdata); break;
    case Py_LT: res = (v_cdata <  w_cdata); break;
    case Py_LE: res = (v_cdata <= w_cdata); break;
    case Py_GT: res = (v_cdata >  w_cdata); break;
    case Py_GE: res = (v_cdata >= w_cdata); break;
    default: res = -1;
    }
    pyres = res ? Py_True : Py_False;
 done:
    Py_INCREF(pyres);
    return pyres;

 Unimplemented:
    pyres = Py_NotImplemented;
    goto done;

 Error:
    PyErr_SetString(PyExc_TypeError,
                    "cannot do comparison on a primitive cdata");
    return NULL;
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

static char *
_cdata_get_indexed_ptr(CDataObject *cd, PyObject *key)
{
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
    return cd->c_data + i * cd->c_type->ct_itemdescr->ct_size;
}

static PyObject *
cdataowning_subscript(CDataObject *cd, PyObject *key)
{
    char *c = _cdata_get_indexed_ptr(cd, key);
    /* use 'mp_subscript' instead of 'sq_item' because we don't want
       negative indexes to be corrected automatically */
    if (c == NULL && PyErr_Occurred())
        return NULL;

    if (cd->c_type->ct_flags & CT_IS_PTR_TO_OWNED) {
        PyObject *res = ((CDataObject_own_structptr *)cd)->structobj;
        Py_INCREF(res);
        return res;
    }
    else {
        return convert_to_object(c, cd->c_type->ct_itemdescr);
    }
}

static PyObject *
cdata_subscript(CDataObject *cd, PyObject *key)
{
    char *c = _cdata_get_indexed_ptr(cd, key);
    /* use 'mp_subscript' instead of 'sq_item' because we don't want
       negative indexes to be corrected automatically */
    if (c == NULL && PyErr_Occurred())
        return NULL;
    return convert_to_object(c, cd->c_type->ct_itemdescr);
}

static int
cdata_ass_sub(CDataObject *cd, PyObject *key, PyObject *v)
{
    char *c = _cdata_get_indexed_ptr(cd, key);
    CTypeDescrObject *ctitem = cd->c_type->ct_itemdescr;
    /* use 'mp_ass_subscript' instead of 'sq_ass_item' because we don't want
       negative indexes to be corrected automatically */
    if (c == NULL && PyErr_Occurred())
        return -1;
    if (v == NULL) {
        PyErr_SetString(PyExc_TypeError,
                        "'del x[n]' not supported for cdata objects");
        return -1;
    }
    return convert_from_object(c, ctitem, v);
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
    Py_INCREF(Py_NotImplemented);
    return Py_NotImplemented;
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
                         cdv->c_type->ct_name, ct->ct_name);
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
            if (cf->cf_bitshift >= 0)
                return convert_to_object_bitfield(data, cf);
            else
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
                return convert_field_from_object(data, cf, value);
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

static PyObject *
convert_struct_to_owning_object(char *data, CTypeDescrObject *ct); /*forward*/

static cif_description_t *
fb_prepare_cif(PyObject *fargs, CTypeDescrObject *, ffi_abi);      /*forward*/

static PyObject *
b_new_primitive_type(PyObject *self, PyObject *args);              /*forward*/

static CTypeDescrObject *_get_ct_int(void)
{
    static CTypeDescrObject *ct_int = NULL;
    if (ct_int == NULL) {
        PyObject *args = Py_BuildValue("(s)", "int");
        if (args == NULL)
            return NULL;
        ct_int = (CTypeDescrObject *)b_new_primitive_type(NULL, args);
        Py_DECREF(args);
    }
    return ct_int;
}

static PyObject*
cdata_call(CDataObject *cd, PyObject *args, PyObject *kwds)
{
    char *buffer;
    void** buffer_array;
    cif_description_t *cif_descr;
    Py_ssize_t i, nargs, nargs_declared;
    PyObject *signature, *res, *fvarargs;
    CTypeDescrObject *fresult;
    char *resultdata;
    char *errormsg;

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
    nargs = PyTuple_Size(args);
    if (nargs < 0)
        return NULL;
    nargs_declared = PyTuple_GET_SIZE(signature) - 2;
    fresult = (CTypeDescrObject *)PyTuple_GET_ITEM(signature, 1);
    fvarargs = NULL;
    buffer = NULL;

    cif_descr = (cif_description_t *)cd->c_type->ct_extra;

    if (cif_descr != NULL) {
        /* regular case: this function does not take '...' arguments */
        if (nargs != nargs_declared) {
            errormsg = "'%s' expects %zd arguments, got %zd";
            goto bad_number_of_arguments;
        }
    }
    else {
        /* call of a variadic function */
        ffi_abi fabi;
        if (nargs < nargs_declared) {
            errormsg = "'%s' expects at least %zd arguments, got %zd";
            goto bad_number_of_arguments;
        }
        fvarargs = PyTuple_New(nargs);
        if (fvarargs == NULL)
            goto error;
        for (i = 0; i < nargs_declared; i++) {
            PyObject *o = PyTuple_GET_ITEM(signature, 2 + i);
            Py_INCREF(o);
            PyTuple_SET_ITEM(fvarargs, i, o);
        }
        for (i = nargs_declared; i < nargs; i++) {
            PyObject *obj = PyTuple_GET_ITEM(args, i);
            CTypeDescrObject *ct;

            if (CData_Check(obj)) {
                ct = ((CDataObject *)obj)->c_type;
                if (ct->ct_flags & (CT_PRIMITIVE_CHAR | CT_PRIMITIVE_UNSIGNED |
                                    CT_PRIMITIVE_SIGNED)) {
                    if (ct->ct_size < sizeof(int)) {
                        ct = _get_ct_int();
                        if (ct == NULL)
                            goto error;
                    }
                }
                else if (ct->ct_flags & CT_ARRAY) {
                    ct = (CTypeDescrObject *)ct->ct_stuff;
                }
                Py_INCREF(ct);
            }
            else {
                PyErr_Format(PyExc_TypeError,
                             "argument %zd passed in the variadic part "
                             "needs to be a cdata object (got %.200s)",
                             i + 1, Py_TYPE(obj)->tp_name);
                goto error;
            }
            PyTuple_SET_ITEM(fvarargs, i, (PyObject *)ct);
        }
        fabi = PyInt_AS_LONG(PyTuple_GET_ITEM(signature, 0));
        cif_descr = fb_prepare_cif(fvarargs, fresult, fabi);
        if (cif_descr == NULL)
            goto error;
    }

    buffer = PyObject_Malloc(cif_descr->exchange_size);
    if (buffer == NULL) {
        PyErr_NoMemory();
        goto error;
    }

    buffer_array = (void **)buffer;

    for (i=0; i<nargs; i++) {
        CTypeDescrObject *argtype;
        char *data = buffer + cif_descr->exchange_offset_arg[1 + i];
        PyObject *obj = PyTuple_GET_ITEM(args, i);

        buffer_array[i] = data;

        if (i < nargs_declared)
            argtype = (CTypeDescrObject *)PyTuple_GET_ITEM(signature, 2 + i);
        else
            argtype = (CTypeDescrObject *)PyTuple_GET_ITEM(fvarargs, i);

        if ((argtype->ct_flags & CT_POINTER) &&
            (argtype->ct_itemdescr->ct_flags & CT_PRIMITIVE_CHAR)) {
            if (argtype->ct_itemdescr->ct_size == sizeof(char)) {
                if (PyString_Check(obj)) {
                    /* special case: Python string -> cdata 'char *' */
                    *(char **)data = PyString_AS_STRING(obj);
                    continue;
                }
            }
#ifdef HAVE_WCHAR_H
            else {
                if (PyUnicode_Check(obj)) {
                    /* Python Unicode string -> cdata 'wchar_t *':
                       not supported yet */
                    PyErr_SetString(PyExc_NotImplementedError,
                        "automatic unicode-to-'wchar_t *' conversion");
                    goto error;
                }
            }
#endif
        }
        if (convert_from_object(data, argtype, obj) < 0)
            goto error;
    }

    resultdata = buffer + cif_descr->exchange_offset_arg[0];

    restore_errno();
    ffi_call(&cif_descr->cif, (void (*)(void))(cd->c_data),
             resultdata, buffer_array);
    save_errno();

    if (fresult->ct_flags & (CT_PRIMITIVE_CHAR | CT_PRIMITIVE_SIGNED |
                             CT_PRIMITIVE_UNSIGNED)) {
#ifdef WORDS_BIGENDIAN
        /* For results of precisely these types, libffi has a strange
           rule that they will be returned as a whole 'ffi_arg' if they
           are smaller.  The difference only matters on big-endian. */
        if (fresult->ct_size < sizeof(ffi_arg))
            resultdata += (sizeof(ffi_arg) - fresult->ct_size);
#endif
        res = convert_to_object(resultdata, fresult);
    }
    else if (fresult->ct_flags & CT_VOID) {
        res = Py_None;
        Py_INCREF(res);
    }
    else if (fresult->ct_flags & CT_STRUCT) {
        res = convert_struct_to_owning_object(resultdata, fresult);
    }
    else {
        res = convert_to_object(resultdata, fresult);
    }
    PyObject_Free(buffer);
 done:
    if (fvarargs != NULL) {
        Py_DECREF(fvarargs);
        if (cif_descr != NULL)  /* but only if fvarargs != NULL, if variadic */
            PyObject_Free(cif_descr);
    }
    return res;

 bad_number_of_arguments:
    PyErr_Format(PyExc_TypeError, errormsg,
                 cd->c_type->ct_name, nargs_declared, nargs);
 error:
    if (buffer)
        PyObject_Free(buffer);
    res = NULL;
    goto done;
}

static PyObject *cdata_iter(CDataObject *);

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

static PyMappingMethods CDataOwn_as_mapping = {
    (lenfunc)cdata_length, /*mp_length*/
    (binaryfunc)cdataowning_subscript, /*mp_subscript*/
    (objobjargproc)cdata_ass_sub, /*mp_ass_subscript*/
};

static PyMethodDef CData_methods[] = {
    {"__unicode__",     (PyCFunction)cdata_unicode,  METH_NOARGS},
    {NULL,              NULL}           /* sentinel */
};

static PyTypeObject CData_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_cffi_backend.CData",
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
    0,                                          /* tp_weaklistoffset */
    (getiterfunc)cdata_iter,                    /* tp_iter */
    0,                                          /* tp_iternext */
    CData_methods,                              /* tp_methods */
};

static PyTypeObject CDataOwning_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_cffi_backend.CDataOwn",
    sizeof(CDataObject_own_base),
    0,
    (destructor)cdataowning_dealloc,            /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    (reprfunc)cdataowning_repr,                 /* tp_repr */
    0,                                          /* tp_as_number */
    0,                                          /* tp_as_sequence */
    &CDataOwn_as_mapping,                       /* tp_as_mapping */
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
    offsetof(CDataObject_own_base, weakreflist),/* tp_weaklistoffset */
    0,                                          /* tp_iter */
    0,                                          /* tp_iternext */
    0,                                          /* tp_methods */
    0,                                          /* tp_members */
    0,                                          /* tp_getset */
    &CData_Type,                                /* tp_base */
};

/************************************************************/

typedef struct {
    PyObject_HEAD
    char *di_next, *di_stop;
    CDataObject *di_object;
    CTypeDescrObject *di_itemtype;
} CDataIterObject;

static PyObject *
cdataiter_next(CDataIterObject *it)
{
    char *result = it->di_next;
    if (result != it->di_stop) {
        it->di_next = result + it->di_itemtype->ct_size;
        return convert_to_object(result, it->di_itemtype);
    }
    return NULL;
}

static void
cdataiter_dealloc(CDataIterObject *it)
{
    Py_DECREF(it->di_object);
    PyObject_Del(it);
}

static PyTypeObject CDataIter_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_cffi_backend.CDataIter",              /* tp_name */
    sizeof(CDataIterObject),                /* tp_basicsize */
    0,                                      /* tp_itemsize */
    /* methods */
    (destructor)cdataiter_dealloc,          /* tp_dealloc */
    0,                                      /* tp_print */
    0,                                      /* tp_getattr */
    0,                                      /* tp_setattr */
    0,                                      /* tp_compare */
    0,                                      /* tp_repr */
    0,                                      /* tp_as_number */
    0,                                      /* tp_as_sequence */
    0,                                      /* tp_as_mapping */
    0,                                      /* tp_hash */
    0,                                      /* tp_call */
    0,                                      /* tp_str */
    PyObject_GenericGetAttr,                /* tp_getattro */
    0,                                      /* tp_setattro */
    0,                                      /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                     /* tp_flags */
    0,                                      /* tp_doc */
    0,                                      /* tp_traverse */
    0,                                      /* tp_clear */
    0,                                      /* tp_richcompare */
    0,                                      /* tp_weaklistoffset */
    PyObject_SelfIter,                      /* tp_iter */
    (iternextfunc)cdataiter_next,           /* tp_iternext */
};

static PyObject *
cdata_iter(CDataObject *cd)
{
    CDataIterObject *it;

    if (!(cd->c_type->ct_flags & CT_ARRAY)) {
        PyErr_Format(PyExc_TypeError, "cdata '%s' does not support iteration",
                     cd->c_type->ct_name);
        return NULL;
    }

    it = PyObject_New(CDataIterObject, &CDataIter_Type);
    if (it == NULL)
        return NULL;

    Py_INCREF(cd);
    it->di_object = cd;
    it->di_itemtype = cd->c_type->ct_itemdescr;
    it->di_next = cd->c_data;
    it->di_stop = cd->c_data + get_array_length(cd) * it->di_itemtype->ct_size;
    return (PyObject *)it;
}

/************************************************************/

static CDataObject_own_base *allocate_owning_object(Py_ssize_t size,
                                                    CTypeDescrObject *ct)
{
    CDataObject_own_base *cdb;
    cdb = (CDataObject_own_base *)PyObject_Malloc(size);
    if (PyObject_Init((PyObject *)cdb, &CDataOwning_Type) == NULL)
        return NULL;

    Py_INCREF(ct);
    cdb->head.c_type = ct;
    cdb->weakreflist = NULL;
    return cdb;
}

static PyObject *
convert_struct_to_owning_object(char *data, CTypeDescrObject *ct)
{
    CDataObject_own_base *cdb;
    Py_ssize_t dataoffset = offsetof(CDataObject_own_nolength, alignment);
    Py_ssize_t datasize = ct->ct_size;

    if ((ct->ct_flags & (CT_STRUCT|CT_IS_OPAQUE)) != CT_STRUCT) {
        PyErr_SetString(PyExc_TypeError,
                        "return type is not a struct or is opaque");
        return NULL;
    }
    cdb = allocate_owning_object(dataoffset + datasize, ct);
    if (cdb == NULL)
        return NULL;
    cdb->head.c_data = ((char *)cdb) + dataoffset;

    memcpy(cdb->head.c_data, data, datasize);
    return (PyObject *)cdb;
}

static PyObject *b_newp(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct, *ctitem;
    CDataObject *cd;
    CDataObject_own_base *cdb;
    PyObject *init = Py_None;
    Py_ssize_t dataoffset, datasize, explicitlength;
    if (!PyArg_ParseTuple(args, "O!|O:newp", &CTypeDescr_Type, &ct, &init))
        return NULL;

    explicitlength = -1;
    if (ct->ct_flags & CT_POINTER) {
        dataoffset = offsetof(CDataObject_own_nolength, alignment);
        ctitem = ct->ct_itemdescr;
        datasize = ctitem->ct_size;
        if (datasize < 0) {
            PyErr_Format(PyExc_TypeError,
                         "cannot instantiate ctype '%s' of unknown size",
                         ctitem->ct_name);
            return NULL;
        }
        if (ctitem->ct_flags & CT_PRIMITIVE_CHAR)
            datasize *= 2;   /* forcefully add another character: a null */
    }
    else if (ct->ct_flags & CT_ARRAY) {
        dataoffset = offsetof(CDataObject_own_nolength, alignment);
        datasize = ct->ct_size;
        if (datasize < 0) {
            if (PyList_Check(init) || PyTuple_Check(init)) {
                explicitlength = PySequence_Fast_GET_SIZE(init);
            }
            else if (PyString_Check(init)) {
                /* from a string, we add the null terminator */
                explicitlength = PyString_GET_SIZE(init) + 1;
            }
            else if (PyUnicode_Check(init)) {
                /* from a unicode, we add the null terminator */
                explicitlength = _my_PyUnicode_SizeAsWideChar(init) + 1;
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
    else {
        PyErr_Format(PyExc_TypeError,
                     "expected a pointer or array ctype, got '%s'",
                     ct->ct_name);
        return NULL;
    }

    if (ct->ct_flags & CT_IS_PTR_TO_OWNED) {
        /* common case of ptr-to-struct (or ptr-to-union): for this case
           we build two objects instead of one, with the memory-owning
           one being really the struct (or union) and the returned one
           having a strong reference to it */
        CDataObject_own_base *cdp;

        cdb = allocate_owning_object(dataoffset + datasize, ct->ct_itemdescr);
        if (cdb == NULL)
            return NULL;

        cdp = allocate_owning_object(sizeof(CDataObject_own_structptr), ct);
        if (cdp == NULL) {
            Py_DECREF(cdb);
            return NULL;
        }
        /* store the only reference to cdb into cdp */
        ((CDataObject_own_structptr *)cdp)->structobj = (PyObject *)cdb;
        assert(explicitlength < 0);

        cdb->head.c_data = cdp->head.c_data = ((char *)cdb) + dataoffset;
        cd = &cdp->head;
    }
    else {
        cdb = allocate_owning_object(dataoffset + datasize, ct);
        if (cdb == NULL)
            return NULL;

        cdb->head.c_data = ((char *)cdb) + dataoffset;
        if (explicitlength >= 0)
            ((CDataObject_own_length*)cdb)->length = explicitlength;
        cd = &cdb->head;
    }

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
    int dataoffset = offsetof(CDataObject_casted_primitive, alignment);
    CDataObject *cd = (CDataObject *)PyObject_Malloc(dataoffset + ct->ct_size);
    if (PyObject_Init((PyObject *)cd, &CData_Type) == NULL)
        return NULL;
    Py_INCREF(ct);
    cd->c_type = ct;
    cd->c_data = ((char*)cd) + dataoffset;
    return cd;
}

static CDataObject *cast_to_integer_or_char(CTypeDescrObject *ct, PyObject *ob)
{
    unsigned PY_LONG_LONG value;
    CDataObject *cd;

    if (CData_Check(ob) &&
        ((CDataObject *)ob)->c_type->ct_flags &
                                 (CT_POINTER|CT_FUNCTIONPTR|CT_ARRAY)) {
        value = (Py_intptr_t)((CDataObject *)ob)->c_data;
    }
    else if (PyString_Check(ob)) {
        if (ct->ct_flags & CT_IS_ENUM) {
            ob = convert_enum_string_to_int(ct, ob);
            if (ob == NULL)
                return NULL;
            cd = cast_to_integer_or_char(ct, ob);
            Py_DECREF(ob);
            return cd;
        }
        else {
            if (PyString_GET_SIZE(ob) != 1) {
                PyErr_Format(PyExc_TypeError,
                      "cannot cast string of length %zd to ctype '%s'",
                             PyString_GET_SIZE(ob), ct->ct_name);
                return NULL;
            }
            value = (unsigned char)PyString_AS_STRING(ob)[0];
        }
    }
#ifdef HAVE_WCHAR_H
    else if (PyUnicode_Check(ob)) {
        wchar_t ordinal;
        if (_my_PyUnicode_AsSingleWideChar(ob, &ordinal) < 0) {
            PyErr_Format(PyExc_TypeError,
                         "cannot cast unicode of length %zd to ctype '%s'",
                         PyUnicode_GET_SIZE(ob), ct->ct_name);
            return NULL;
        }
        value = (long)ordinal;
    }
#endif
    else {
        value = _my_PyLong_AsUnsignedLongLong(ob, 0);
        if (value == (unsigned PY_LONG_LONG)-1 && PyErr_Occurred())
            return NULL;
    }
    cd = _new_casted_primitive(ct);
    if (cd != NULL)
        write_raw_integer_data(cd->c_data, value, ct->ct_size);
    return cd;
}

static PyObject *b_cast(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    CDataObject *cd;
    PyObject *ob;
    if (!PyArg_ParseTuple(args, "O!O:cast", &CTypeDescr_Type, &ct, &ob))
        return NULL;

    if (ct->ct_flags & (CT_POINTER|CT_FUNCTIONPTR|CT_ARRAY) &&
        ct->ct_size >= 0) {
        /* cast to a pointer, to a funcptr, or to an array.
           Note that casting to an array is an extension to the C language,
           which seems to be necessary in order to sanely get a
           <cdata 'int[3]'> at some address. */
        unsigned PY_LONG_LONG value;

        if (CData_Check(ob)) {
            CDataObject *cdsrc = (CDataObject *)ob;
            if (cdsrc->c_type->ct_flags &
                    (CT_POINTER|CT_FUNCTIONPTR|CT_ARRAY)) {
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
        return (PyObject *)cast_to_integer_or_char(ct, ob);
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
    else {
        PyErr_Format(PyExc_TypeError, "cannot cast to ctype '%s'",
                     ct->ct_name);
        return NULL;
    }

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
    char *dl_name;
} DynLibObject;

static void dl_dealloc(DynLibObject *dlobj)
{
    dlclose(dlobj->dl_handle);
    free(dlobj->dl_name);
    PyObject_Del(dlobj);
}

static PyObject *dl_repr(DynLibObject *dlobj)
{
    return PyString_FromFormat("<clibrary '%s'>", dlobj->dl_name);
}

static PyObject *dl_load_function(DynLibObject *dlobj, PyObject *args)
{
    CTypeDescrObject *ct;
    char *funcname;
    void *funcptr;
    int ok;

    if (!PyArg_ParseTuple(args, "O!s:load_function",
                          &CTypeDescr_Type, &ct, &funcname))
        return NULL;

    ok = 0;
    if (ct->ct_flags & CT_FUNCTIONPTR)
        ok = 1;
    if ((ct->ct_flags & CT_POINTER) && (ct->ct_itemdescr->ct_flags & CT_VOID))
        ok = 1;
    if (!ok) {
        PyErr_Format(PyExc_TypeError, "function cdata expected, got '%s'",
                     ct->ct_name);
        return NULL;
    }
    funcptr = dlsym(dlobj->dl_handle, funcname);
    if (funcptr == NULL) {
        PyErr_Format(PyExc_KeyError, "function '%s' not found in library '%s'",
                     funcname, dlobj->dl_name);
        return NULL;
    }

    return new_simple_cdata(funcptr, ct);
}

static PyObject *dl_read_variable(DynLibObject *dlobj, PyObject *args)
{
    CTypeDescrObject *ct;
    char *varname;
    char *data;

    if (!PyArg_ParseTuple(args, "O!s:read_variable",
                          &CTypeDescr_Type, &ct, &varname))
        return NULL;

    data = dlsym(dlobj->dl_handle, varname);
    if (data == NULL) {
        PyErr_Format(PyExc_KeyError, "variable '%s' not found in library '%s'",
                     varname, dlobj->dl_name);
        return NULL;
    }
    return convert_to_object(data, ct);
}

static PyObject *dl_write_variable(DynLibObject *dlobj, PyObject *args)
{
    CTypeDescrObject *ct;
    PyObject *value;
    char *varname;
    char *data;

    if (!PyArg_ParseTuple(args, "O!sO:read_variable",
                          &CTypeDescr_Type, &ct, &varname, &value))
        return NULL;

    data = dlsym(dlobj->dl_handle, varname);
    if (data == NULL) {
        PyErr_Format(PyExc_KeyError, "variable '%s' not found in library '%s'",
                     varname, dlobj->dl_name);
        return NULL;
    }
    if (convert_from_object(data, ct, value) < 0)
        return NULL;
    Py_INCREF(Py_None);
    return Py_None;
}

static PyMethodDef dl_methods[] = {
    {"load_function",   (PyCFunction)dl_load_function,  METH_VARARGS},
    {"read_variable",   (PyCFunction)dl_read_variable,  METH_VARARGS},
    {"write_variable",  (PyCFunction)dl_write_variable, METH_VARARGS},
    {NULL,              NULL}           /* sentinel */
};

static PyTypeObject dl_type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "_cffi_backend.Library",            /* tp_name */
    sizeof(DynLibObject),               /* tp_basicsize */
    0,                                  /* tp_itemsize */
    /* methods */
    (destructor)dl_dealloc,             /* tp_dealloc */
    0,                                  /* tp_print */
    0,                                  /* tp_getattr */
    0,                                  /* tp_setattr */
    0,                                  /* tp_compare */
    (reprfunc)dl_repr,                  /* tp_repr */
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
    DynLibObject *dlobj;
    int is_global = 0;

    if (!PyArg_ParseTuple(args, "et|i:load_library",
                          Py_FileSystemDefaultEncoding, &filename,
                          &is_global))
        return NULL;

    handle = dlopen(filename, RTLD_LAZY | (is_global?RTLD_GLOBAL:RTLD_LOCAL));
    if (handle == NULL) {
        PyErr_Format(PyExc_OSError, "cannot load library: %s", filename);
        return NULL;
    }

    dlobj = PyObject_New(DynLibObject, &dl_type);
    if (dlobj == NULL) {
        dlclose(handle);
        return NULL;
    }
    dlobj->dl_handle = handle;
    dlobj->dl_name = strdup(filename);
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
       EPTYPE(c, char, CT_PRIMITIVE_CHAR)                       \
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
#ifdef HAVE_WCHAR_H
# define ENUM_PRIMITIVE_TYPES_WCHAR                             \
       EPTYPE(wc, wchar_t, CT_PRIMITIVE_CHAR )
#else
# define ENUM_PRIMITIVE_TYPES_WCHAR   /* nothing */
#endif

#define EPTYPE(code, typename, flags)                   \
    struct aligncheck_##code { char x; typename y; };
    ENUM_PRIMITIVE_TYPES
    ENUM_PRIMITIVE_TYPES_WCHAR
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
    ENUM_PRIMITIVE_TYPES_WCHAR
#undef EPTYPE
#undef ENUM_PRIMITIVE_TYPES_WCHAR
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
#ifndef HAVE_WCHAR_H
            if (strcmp(name, "wchar_t"))
                PyErr_SetString(PyExc_NotImplementedError, name);
            else
#endif
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
    if (td->ct_flags & (CT_PRIMITIVE_SIGNED | CT_PRIMITIVE_CHAR)) {
        if (td->ct_size <= sizeof(long))
            td->ct_flags |= CT_PRIMITIVE_FITS_LONG;
    }
    else if (td->ct_flags & CT_PRIMITIVE_UNSIGNED) {
        if (td->ct_size < sizeof(long))
            td->ct_flags |= CT_PRIMITIVE_FITS_LONG;
    }
    td->ct_name_position = strlen(td->ct_name);
    return (PyObject *)td;

 bad_ffi_type:
    PyErr_Format(PyExc_NotImplementedError,
                 "primitive type '%s' with a non-standard size %d",
                 name, (int)ptypes->size);
    return NULL;
}

static PyObject *b_new_pointer_type(PyObject *self, PyObject *args)
{
    CTypeDescrObject *td, *ctitem;
    const char *extra;

    if (!PyArg_ParseTuple(args, "O!:new_pointer_type",
                          &CTypeDescr_Type, &ctitem))
        return NULL;

    if (ctitem->ct_flags & CT_ARRAY)
        extra = "(*)";   /* obscure case: see test_array_add */
    else
        extra = " *";
    td = ctypedescr_new_on_top(ctitem, extra, 2);
    if (td == NULL)
        return NULL;

    td->ct_size = sizeof(void *);
    td->ct_flags = CT_POINTER;
    if (ctitem->ct_flags & (CT_STRUCT|CT_UNION))
        td->ct_flags |= CT_IS_PTR_TO_OWNED;
    if ((ctitem->ct_flags & CT_VOID) ||
        ((ctitem->ct_flags & CT_PRIMITIVE_CHAR) &&
         ctitem->ct_size == sizeof(char)))
        td->ct_flags |= CT_CAST_ANYTHING;   /* 'void *' or 'char *' only */
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
        sprintf(extra_text, "[%llu]", (unsigned PY_LONG_LONG)length);
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
    td->ct_flags = CT_VOID | CT_IS_OPAQUE;
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
    td->ct_length = -1;
    td->ct_flags = flag | CT_IS_OPAQUE;
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
    PyObject *fields, *interned_fields, *ignored;
    int is_union, alignment;
    Py_ssize_t offset, i, nb_fields, maxsize, prev_bit_position;
    Py_ssize_t totalsize = -1;
    int totalalignment = -1;
    CFieldObject **previous, *prev_field;

    if (!PyArg_ParseTuple(args, "O!O!|Oni:complete_struct_or_union",
                          &CTypeDescr_Type, &ct,
                          &PyList_Type, &fields,
                          &ignored, &totalsize, &totalalignment))
        return NULL;

    if ((ct->ct_flags & (CT_STRUCT|CT_IS_OPAQUE)) ==
                        (CT_STRUCT|CT_IS_OPAQUE)) {
        is_union = 0;
    }
    else if ((ct->ct_flags & (CT_UNION|CT_IS_OPAQUE)) ==
                             (CT_UNION|CT_IS_OPAQUE)) {
        is_union = 1;
    }
    else {
        PyErr_SetString(PyExc_TypeError,
                  "first arg must be a non-initialized struct or union ctype");
        return NULL;
    }

    maxsize = 0;
    alignment = 1;
    offset = 0;
    nb_fields = PyList_GET_SIZE(fields);
    interned_fields = PyDict_New();
    if (interned_fields == NULL)
        return NULL;

    previous = (CFieldObject **)&ct->ct_extra;
    prev_bit_position = 0;
    prev_field = NULL;

    for (i=0; i<nb_fields; i++) {
        PyObject *fname;
        CTypeDescrObject *ftype;
        int fbitsize = -1, falign, err, bitshift, foffset = -1;
        CFieldObject *cf;

        if (!PyArg_ParseTuple(PyList_GET_ITEM(fields, i), "O!O!|ii:list item",
                              &PyString_Type, &fname,
                              &CTypeDescr_Type, &ftype,
                              &fbitsize, &foffset))
            goto error;

        if (ftype->ct_size < 0) {
            PyErr_Format(PyExc_TypeError,
                         "field '%s.%s' has ctype '%s' of unknown size",
                         ct->ct_name, PyString_AS_STRING(fname),
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

        if (foffset >= 0) {
            /* a forced field position: ignore the offset just computed,
               except to know if we must set CT_CUSTOM_FIELD_POS */
            if (offset != foffset)
                ct->ct_flags |= CT_CUSTOM_FIELD_POS;
            offset = foffset;
        }

        if (fbitsize < 0 || (fbitsize == 8 * ftype->ct_size &&
                             !(ftype->ct_flags & CT_PRIMITIVE_CHAR))) {
            fbitsize = -1;
            bitshift = -1;
            prev_bit_position = 0;
        }
        else {
            if (!(ftype->ct_flags & (CT_PRIMITIVE_SIGNED |
                                     CT_PRIMITIVE_UNSIGNED |
                                     CT_PRIMITIVE_CHAR)) ||
#ifdef HAVE_WCHAR_H
                    ((ftype->ct_flags & CT_PRIMITIVE_CHAR)
                         && ftype->ct_size == sizeof(wchar_t)) ||
#endif
                    fbitsize == 0 ||
                    fbitsize > 8 * ftype->ct_size) {
                PyErr_Format(PyExc_TypeError, "invalid bit field '%s'",
                             PyString_AS_STRING(fname));
                goto error;
            }
            if (prev_bit_position > 0) {
                assert(prev_field && prev_field->cf_bitshift >= 0);
                if (prev_field->cf_type->ct_size != ftype->ct_size) {
                    PyErr_SetString(PyExc_NotImplementedError,
                                    "consecutive bit fields should be "
                                    "declared with a same-sized type");
                    goto error;
                }
                else if (prev_bit_position + fbitsize > 8 * ftype->ct_size) {
                    prev_bit_position = 0;
                }
                else {
                    /* we can share the same field as 'prev_field' */
                    offset = prev_field->cf_offset;
                }
            }
            bitshift = prev_bit_position;
            if (!is_union)
                prev_bit_position += fbitsize;
        }

        cf = PyObject_New(CFieldObject, &CField_Type);
        if (cf == NULL)
            goto error;
        Py_INCREF(ftype);
        cf->cf_type = ftype;
        cf->cf_offset = offset;
        cf->cf_bitshift = bitshift;
        cf->cf_bitsize = fbitsize;

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
        prev_field = cf;

        if (maxsize < ftype->ct_size)
            maxsize = ftype->ct_size;
        if (!is_union)
            offset += ftype->ct_size;
    }
    *previous = NULL;

    if (is_union) {
        assert(offset == 0);
        offset = maxsize;
    }
    else {
        offset = (offset + alignment - 1) & ~(alignment-1);
    }
    /* Like C, if the size of this structure would be zero, we compute it
       as 1 instead.  But for ctypes support, we allow the manually-
       specified totalsize to be zero in this case. */
    if (totalsize < 0) {
        totalsize = (offset == 0 ? 1 : offset);
    }
    else if (totalsize < offset) {
        PyErr_Format(PyExc_TypeError,
                     "%s cannot be of size %zd: there are fields at least "
                     "up to %zd", ct->ct_name, totalsize, offset);
        goto error;
    }
    ct->ct_size = totalsize;
    ct->ct_length = totalalignment < 0 ? alignment : totalalignment;
    ct->ct_stuff = interned_fields;
    ct->ct_flags &= ~CT_IS_OPAQUE;

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

    if (!CTypeDescr_Check(arg)) {
        PyErr_SetString(PyExc_TypeError,"expected a 'ctype' object");
        return NULL;
    }
    d = (PyObject *)ct->ct_stuff;
    if (d == NULL) {
        res = Py_None;
        Py_INCREF(res);
    }
    else if (ct->ct_flags & (CT_STRUCT|CT_UNION)) {
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
    else if (ct->ct_flags & CT_IS_ENUM) {
        res = PyDict_Items(PyTuple_GET_ITEM(d, 1));
        if (res == NULL)
            return NULL;
        if (PyList_Sort(res) < 0)
            Py_CLEAR(res);
    }
    else {
        res = d;
        Py_INCREF(res);
    }
    return res;
}

struct funcbuilder_s {
    Py_ssize_t nb_bytes;
    char *bufferp;
    ffi_type **atypes;
    ffi_type *rtype;
    Py_ssize_t nargs;
    CTypeDescrObject *fct;
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

static ffi_type *fb_fill_type(struct funcbuilder_s *fb, CTypeDescrObject *ct,
                              int is_result_type)
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

    if (ct->ct_size <= 0) {
        PyErr_Format(PyExc_TypeError,
                     ct->ct_size < 0 ? "ctype '%s' has incomplete type"
                                     : "ctype '%s' has size 0",
                     ct->ct_name);
        return NULL;
    }
    if (ct->ct_flags & CT_STRUCT) {
        ffi_type *ffistruct, *ffifield;
        ffi_type **elements;
        Py_ssize_t i, n;
        CFieldObject *cf;

        /* We can't pass a struct that was completed by verify().
           Issue: assume verify() is given "struct { long b; ...; }".
           Then it will complete it in the same way whether it is actually
           "struct { long a, b; }" or "struct { double a; long b; }".
           But on 64-bit UNIX, these two structs are passed by value
           differently: e.g. on x86-64, "b" ends up in register "rsi" in
           the first case and "rdi" in the second case.
        */
        if (ct->ct_flags & CT_CUSTOM_FIELD_POS) {
            PyErr_SetString(PyExc_TypeError,
                "cannot pass as an argument a struct that was completed "
                "with verify() (see _cffi_backend.c for details of why)");
            return NULL;
        }

#ifdef USE_C_LIBFFI_MSVC
        /* MSVC returns small structures in registers.  Pretend int32 or
           int64 return type.  This is needed as a workaround for what
           is really a bug of libffi_msvc seen as an independent library
           (ctypes has a similar workaround). */
        if (is_result_type) {
            if (ct->ct_size <= 4)
                return &ffi_type_sint32;
            if (ct->ct_size <= 8)
                return &ffi_type_sint64;
        }
#endif

        n = PyDict_Size(ct->ct_stuff);
        elements = fb_alloc(fb, (n + 1) * sizeof(ffi_type*));
        cf = (CFieldObject *)ct->ct_extra;

        for (i=0; i<n; i++) {
            assert(cf != NULL);
            if (cf->cf_bitshift >= 0) {
                PyErr_SetString(PyExc_NotImplementedError,
                    "cannot pass as argument a struct with bit fields");
                return NULL;
            }
            ffifield = fb_fill_type(fb, cf->cf_type, 0);
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
    fb->atypes = fb_alloc(fb, nargs * sizeof(ffi_type*));
    fb->nargs = nargs;

    /* ffi buffer: next comes the result type */
    fb->rtype = fb_fill_type(fb, fresult, 1);
    if (PyErr_Occurred())
        return -1;
    if (cif_descr != NULL) {
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
    else
        exchange_offset = 0;   /* not used */

    /* loop over the arguments */
    for (i=0; i<nargs; i++) {
        CTypeDescrObject *farg;
        ffi_type *atype;

        farg = (CTypeDescrObject *)PyTuple_GET_ITEM(fargs, i);

        /* ffi buffer: fill in the ffi for the i'th argument */
        assert(farg != NULL);
        atype = fb_fill_type(fb, farg, 0);
        if (PyErr_Occurred())
            return -1;

        if (fb->atypes != NULL) {
            fb->atypes[i] = atype;
            /* exchange data size */
            exchange_offset = ALIGN_ARG(exchange_offset);
            cif_descr->exchange_offset_arg[1 + i] = exchange_offset;
            exchange_offset += atype->size;
        }
    }

    if (cif_descr != NULL) {
        /* exchange data size */
        cif_descr->exchange_size = exchange_offset;
    }
    return 0;
}

#undef ALIGN_ARG

static void fb_cat_name(struct funcbuilder_s *fb, char *piece, int piecelen)
{
    if (fb->bufferp == NULL) {
        fb->nb_bytes += piecelen;
    }
    else {
        memcpy(fb->bufferp, piece, piecelen);
        fb->bufferp += piecelen;
    }
}

static int fb_build_name(struct funcbuilder_s *fb, PyObject *fargs,
                         CTypeDescrObject *fresult, int ellipsis)
{
    Py_ssize_t i, nargs = PyTuple_GET_SIZE(fargs);
    fb->nargs = nargs;

    /* name: the function type name we build here is, like in C, made
       as follows:

         RESULT_TYPE_HEAD (*)(ARG_1_TYPE, ARG_2_TYPE, etc) RESULT_TYPE_TAIL
    */
    fb_cat_name(fb, fresult->ct_name, fresult->ct_name_position);
    fb_cat_name(fb, "(*)(", 4);
    if (fb->fct) {
        i = fresult->ct_name_position + 2;  /* between '(*' and ')(' */
        fb->fct->ct_name_position = i;
    }

    /* loop over the arguments */
    for (i=0; i<nargs; i++) {
        CTypeDescrObject *farg;

        farg = (CTypeDescrObject *)PyTuple_GET_ITEM(fargs, i);
        if (!CTypeDescr_Check(farg)) {
            PyErr_SetString(PyExc_TypeError, "expected a tuple of ctypes");
            return -1;
        }
        /* name: concatenate the name of the i'th argument's type */
        if (i > 0)
            fb_cat_name(fb, ", ", 2);
        fb_cat_name(fb, farg->ct_name, strlen(farg->ct_name));
    }

    /* name: add the '...' if needed */
    if (ellipsis) {
        if (nargs > 0)
            fb_cat_name(fb, ", ", 2);
        fb_cat_name(fb, "...", 3);
    }

    /* name: concatenate the tail of the result type */
    fb_cat_name(fb, ")", 1);
    fb_cat_name(fb, fresult->ct_name + fresult->ct_name_position,
                strlen(fresult->ct_name) - fresult->ct_name_position + 1);
    return 0;
}

static CTypeDescrObject *fb_prepare_ctype(struct funcbuilder_s *fb,
                                          PyObject *fargs,
                                          CTypeDescrObject *fresult,
                                          int ellipsis)
{
    CTypeDescrObject *fct;

    fb->nb_bytes = 0;
    fb->bufferp = NULL;
    fb->fct = NULL;

    /* compute the total size needed for the name */
    if (fb_build_name(fb, fargs, fresult, ellipsis) < 0)
        return NULL;

    /* allocate the function type */
    fct = ctypedescr_new(fb->nb_bytes);
    if (fct == NULL)
        return NULL;
    fb->fct = fct;

    /* call again fb_build_name() to really build the ct_name */
    fb->bufferp = fct->ct_name;
    if (fb_build_name(fb, fargs, fresult, ellipsis) < 0)
        goto error;
    assert(fb->bufferp == fct->ct_name + fb->nb_bytes);

    fct->ct_extra = NULL;
    fct->ct_size = sizeof(void(*)(void));
    fct->ct_flags = CT_FUNCTIONPTR;
    return fct;

 error:
    Py_DECREF(fct);
    return NULL;
}

static cif_description_t *fb_prepare_cif(PyObject *fargs,
                                         CTypeDescrObject *fresult,
                                         ffi_abi fabi)
{
    char *buffer;
    cif_description_t *cif_descr;
    struct funcbuilder_s funcbuffer;

    funcbuffer.nb_bytes = 0;
    funcbuffer.bufferp = NULL;

    /* compute the total size needed in the buffer for libffi */
    if (fb_build(&funcbuffer, fargs, fresult) < 0)
        return NULL;

    /* allocate the buffer */
    buffer = PyObject_Malloc(funcbuffer.nb_bytes);
    if (buffer == NULL) {
        PyErr_NoMemory();
        return NULL;
    }

    /* call again fb_build() to really build the libffi data structures */
    funcbuffer.bufferp = buffer;
    if (fb_build(&funcbuffer, fargs, fresult) < 0)
        goto error;
    assert(funcbuffer.bufferp == buffer + funcbuffer.nb_bytes);

    cif_descr = (cif_description_t *)buffer;
    if (ffi_prep_cif(&cif_descr->cif, fabi, funcbuffer.nargs,
                     funcbuffer.rtype, funcbuffer.atypes) != FFI_OK) {
        PyErr_SetString(PyExc_SystemError,
                        "libffi failed to build this function type");
        goto error;
    }
    return cif_descr;

 error:
    PyObject_Free(buffer);
    return NULL;
}

static PyObject *b_new_function_type(PyObject *self, PyObject *args)
{
    PyObject *fargs, *fabiobj;
    CTypeDescrObject *fresult;
    CTypeDescrObject *fct;
    int ellipsis = 0, fabi = FFI_DEFAULT_ABI;
    struct funcbuilder_s funcbuilder;
    Py_ssize_t i;

    if (!PyArg_ParseTuple(args, "O!O!|ii:new_function_type",
                          &PyTuple_Type, &fargs,
                          &CTypeDescr_Type, &fresult,
                          &ellipsis,
                          &fabi))
        return NULL;

    if (fresult->ct_flags & CT_UNION) {
        PyErr_SetString(PyExc_NotImplementedError,
                        "function returning a union");
        return NULL;
    }
    if ((fresult->ct_size < 0 && !(fresult->ct_flags & CT_VOID)) ||
        (fresult->ct_flags & CT_ARRAY)) {
        PyErr_Format(PyExc_TypeError, "invalid result type: '%s'",
                     fresult->ct_name);
        return NULL;
    }

    fct = fb_prepare_ctype(&funcbuilder, fargs, fresult, ellipsis);
    if (fct == NULL)
        return NULL;

    if (!ellipsis) {
        /* Functions with '...' varargs are stored without a cif_descr
           at all.  The cif is computed on every call from the actual
           types passed in.  For all other functions, the cif_descr
           is computed here. */
        cif_description_t *cif_descr;

        cif_descr = fb_prepare_cif(fargs, fresult, fabi);
        if (cif_descr == NULL)
            goto error;

        fct->ct_extra = (char *)cif_descr;
    }

    /* build the signature, given by a tuple of ctype objects */
    fct->ct_stuff = PyTuple_New(2 + funcbuilder.nargs);
    if (fct->ct_stuff == NULL)
        goto error;
    fabiobj = PyInt_FromLong(fabi);
    if (fabiobj == NULL)
        goto error;
    PyTuple_SET_ITEM(fct->ct_stuff, 0, fabiobj);

    Py_INCREF(fresult);
    PyTuple_SET_ITEM(fct->ct_stuff, 1, (PyObject *)fresult);
    for (i=0; i<funcbuilder.nargs; i++) {
        PyObject *o = PyTuple_GET_ITEM(fargs, i);
        /* convert arrays into pointers */
        if (((CTypeDescrObject *)o)->ct_flags & CT_ARRAY)
            o = ((CTypeDescrObject *)o)->ct_stuff;
        Py_INCREF(o);
        PyTuple_SET_ITEM(fct->ct_stuff, 2 + i, o);
    }
    fct->ct_size = sizeof(void(*)(void));
    fct->ct_flags = CT_FUNCTIONPTR;
    return (PyObject *)fct;

 error:
    Py_DECREF(fct);
    return NULL;
}

static int convert_from_object_fficallback(char *result,
                                           CTypeDescrObject *ctype,
                                           PyObject *pyobj)
{
    /* work work work around a libffi irregularity: for integer return
       types we have to fill at least a complete 'ffi_arg'-sized result
       buffer. */
    if (ctype->ct_size < sizeof(ffi_arg)) {
        if ((ctype->ct_flags & (CT_PRIMITIVE_SIGNED | CT_IS_ENUM))
                == CT_PRIMITIVE_SIGNED) {
            PY_LONG_LONG value;
            /* It's probably fine to always zero-extend, but you never
               know: maybe some code somewhere expects a negative
               'short' result to be returned into EAX as a 32-bit
               negative number.  Better safe than sorry.  This code
               is about that case.  Let's ignore this for enums.
            */
            /* do a first conversion only to detect overflows.  This
               conversion produces stuff that is otherwise ignored. */
            if (convert_from_object(result, ctype, pyobj) < 0)
                return -1;
            /* manual inlining and tweaking of convert_from_object()
               in order to write a whole 'ffi_arg'. */
            value = _my_PyLong_AsLongLong(pyobj);
            if (value == -1 && PyErr_Occurred())
                return -1;
            write_raw_integer_data(result, value, sizeof(ffi_arg));
            return 0;
        }
        else if (ctype->ct_flags & (CT_PRIMITIVE_CHAR | CT_PRIMITIVE_SIGNED |
                                    CT_PRIMITIVE_UNSIGNED)) {
            /* zero extension: fill the '*result' with zeros, and (on big-
               endian machines) correct the 'result' pointer to write to */
            memset(result, 0, sizeof(ffi_arg));
#ifdef WORDS_BIGENDIAN
            result += (sizeof(ffi_arg) - ctype->ct_size);
#endif
        }
    }
    return convert_from_object(result, ctype, pyobj);
}

static void invoke_callback(ffi_cif *cif, void *result, void **args,
                            void *userdata)
{
    save_errno();
    {
    PyObject *cb_args = (PyObject *)userdata;
    CTypeDescrObject *ct = (CTypeDescrObject *)PyTuple_GET_ITEM(cb_args, 0);
    PyObject *signature = ct->ct_stuff;
    PyObject *py_ob = PyTuple_GET_ITEM(cb_args, 1);
    PyObject *py_args = NULL;
    PyObject *py_res = NULL;
    PyObject *py_rawerr;
    Py_ssize_t i, n;

#define SIGNATURE(i)  ((CTypeDescrObject *)PyTuple_GET_ITEM(signature, i))

    Py_INCREF(cb_args);

    n = PyTuple_GET_SIZE(signature) - 2;
    py_args = PyTuple_New(n);
    if (py_args == NULL)
        goto error;

    for (i=0; i<n; i++) {
        PyObject *a = convert_to_object(args[i], SIGNATURE(2 + i));
        if (a == NULL)
            goto error;
        PyTuple_SET_ITEM(py_args, i, a);
    }

    py_res = PyEval_CallObject(py_ob, py_args);
    if (py_res == NULL)
        goto error;

    if (SIGNATURE(1)->ct_size > 0) {
        if (convert_from_object_fficallback(result, SIGNATURE(1), py_res) < 0)
            goto error;
    }
    else if (py_res != Py_None) {
        PyErr_SetString(PyExc_TypeError, "callback with the return type 'void'"
                                         " must return None");
        goto error;
    }
 done:
    Py_XDECREF(py_args);
    Py_XDECREF(py_res);
    Py_DECREF(cb_args);
    restore_errno();
    return;

 error:
    PyErr_WriteUnraisable(py_ob);
    if (SIGNATURE(1)->ct_size > 0) {
        py_rawerr = PyTuple_GET_ITEM(cb_args, 2);
        memcpy(result, PyString_AS_STRING(py_rawerr),
                       PyString_GET_SIZE(py_rawerr));
    }
    goto done;
    }

#undef SIGNATURE
}

static PyObject *b_callback(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct, *ctresult;
    CDataObject_own_base *cdb;
    PyObject *ob, *error_ob = Py_None;
    PyObject *py_rawerr, *infotuple = NULL;
    cif_description_t *cif_descr;
    ffi_closure *closure;
    Py_ssize_t size;

    if (!PyArg_ParseTuple(args, "O!O|O:callback", &CTypeDescr_Type, &ct, &ob,
                          &error_ob))
        return NULL;

    if (!(ct->ct_flags & CT_FUNCTIONPTR)) {
        PyErr_Format(PyExc_TypeError, "expected a function ctype, got '%s'",
                     ct->ct_name);
        return NULL;
    }
    if (!PyCallable_Check(ob)) {
        PyErr_Format(PyExc_TypeError,
                     "expected a callable object, not %.200s",
                     Py_TYPE(ob)->tp_name);
        return NULL;
    }

    ctresult = (CTypeDescrObject *)PyTuple_GET_ITEM(ct->ct_stuff, 1);
    size = ctresult->ct_size;
    if (ctresult->ct_flags & (CT_PRIMITIVE_CHAR | CT_PRIMITIVE_SIGNED |
                              CT_PRIMITIVE_UNSIGNED)) {
        if (size < sizeof(ffi_arg))
            size = sizeof(ffi_arg);
    }
    else if (size < 0) {
        size = 0;
    }
    py_rawerr = PyString_FromStringAndSize(NULL, size);
    if (py_rawerr == NULL)
        return NULL;
    memset(PyString_AS_STRING(py_rawerr), 0, size);
    if (error_ob != Py_None) {
        if (convert_from_object_fficallback(
                PyString_AS_STRING(py_rawerr), ctresult, error_ob) < 0) {
            Py_DECREF(py_rawerr);
            return NULL;
        }
    }
    infotuple = Py_BuildValue("OOO", ct, ob, py_rawerr);
    Py_DECREF(py_rawerr);
    if (infotuple == NULL)
        return NULL;

    closure = cffi_closure_alloc();

    cdb = PyObject_New(CDataObject_own_base, &CDataOwning_Type);
    if (cdb == NULL)
        goto error;
    Py_INCREF(ct);
    cdb->head.c_type = ct;
    cdb->head.c_data = (char *)closure;
    cdb->weakreflist = NULL;

    cif_descr = (cif_description_t *)ct->ct_extra;
    if (cif_descr == NULL) {
        PyErr_SetString(PyExc_NotImplementedError,
                        "callbacks with '...'");
        goto error;
    }
    if (ffi_prep_closure(closure, &cif_descr->cif,
                         invoke_callback, infotuple) != FFI_OK) {
        PyErr_SetString(PyExc_SystemError,
                        "libffi failed to build this callback");
        goto error;
    }
    assert(closure->user_data == infotuple);
    return (PyObject *)cdb;

 error:
    closure->user_data = NULL;
    if (cdb == NULL)
        cffi_closure_free(closure);
    else
        Py_DECREF(cdb);
    Py_XDECREF(infotuple);
    return NULL;
}

static PyObject *b_new_enum_type(PyObject *self, PyObject *args)
{
    char *ename;
    PyObject *enumerators, *enumvalues;
    PyObject *dict1 = NULL, *dict2 = NULL, *combined = NULL;
    ffi_type *ffitype;
    int name_size;
    CTypeDescrObject *td;
    Py_ssize_t i, n;
    struct aligncheck_int { char x; int y; };

    if (!PyArg_ParseTuple(args, "sO!O!:new_enum_type",
                          &ename,
                          &PyTuple_Type, &enumerators,
                          &PyTuple_Type, &enumvalues))
        return NULL;

    n = PyTuple_GET_SIZE(enumerators);
    if (n != PyTuple_GET_SIZE(enumvalues)) {
        PyErr_SetString(PyExc_ValueError,
                        "tuple args must have the same size");
        return NULL;
    }

    dict1 = PyDict_New();
    if (dict1 == NULL)
        goto error;
    for (i=n; --i >= 0; ) {
        if (PyDict_SetItem(dict1, PyTuple_GET_ITEM(enumerators, i),
                                  PyTuple_GET_ITEM(enumvalues, i)) < 0)
            goto error;
    }

    dict2 = PyDict_New();
    if (dict2 == NULL)
        goto error;
    for (i=n; --i >= 0; ) {
        if (PyDict_SetItem(dict2, PyTuple_GET_ITEM(enumvalues, i),
                                  PyTuple_GET_ITEM(enumerators, i)) < 0)
            goto error;
    }

    combined = PyTuple_Pack(2, dict1, dict2);
    if (combined == NULL)
        goto error;

    Py_CLEAR(dict2);
    Py_CLEAR(dict1);

    switch (sizeof(int)) {
    case 4: ffitype = &ffi_type_sint32; break;
    case 8: ffitype = &ffi_type_sint64; break;
    default: Py_FatalError("'int' is not 4 or 8 bytes");
    }

    name_size = strlen("enum ") + strlen(ename) + 1;
    td = ctypedescr_new(name_size);
    if (td == NULL)
        goto error;

    memcpy(td->ct_name, "enum ", strlen("enum "));
    memcpy(td->ct_name + strlen("enum "), ename, name_size - strlen("enum "));
    td->ct_stuff = combined;
    td->ct_size = sizeof(int);
    td->ct_length = offsetof(struct aligncheck_int, y);
    td->ct_extra = ffitype;
    td->ct_flags = CT_PRIMITIVE_SIGNED | CT_PRIMITIVE_FITS_LONG | CT_IS_ENUM;
    td->ct_name_position = name_size - 1;
    return (PyObject *)td;

 error:
    Py_XDECREF(combined);
    Py_XDECREF(dict2);
    Py_XDECREF(dict1);
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

static PyObject *b_sizeof(PyObject *self, PyObject *arg)
{
    Py_ssize_t size;

    if (CData_Check(arg)) {
        CDataObject *cd = (CDataObject *)arg;

        if (cd->c_type->ct_flags & CT_ARRAY)
            size = get_array_length(cd) * cd->c_type->ct_itemdescr->ct_size;
        else
            size = cd->c_type->ct_size;
    }
    else if (CTypeDescr_Check(arg)) {
        size = ((CTypeDescrObject *)arg)->ct_size;
        if (size < 0) {
            PyErr_Format(PyExc_ValueError, "ctype '%s' is of unknown size",
                         ((CTypeDescrObject *)arg)->ct_name);
            return NULL;
        }
    }
    else {
        PyErr_SetString(PyExc_TypeError,
                        "expected a 'cdata' or 'ctype' object");
        return NULL;
    }
    return PyInt_FromSsize_t(size);
}

static PyObject *b_typeof(PyObject *self, PyObject *arg)
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

static PyObject *b_getcname(PyObject *self, PyObject *args)
{
    CTypeDescrObject *ct;
    char *replace_with, *p;
    PyObject *s;
    Py_ssize_t namelen, replacelen;

    if (!PyArg_ParseTuple(args, "O!s:getcname",
                          &CTypeDescr_Type, &ct, &replace_with))
        return NULL;

    namelen = strlen(ct->ct_name);
    replacelen = strlen(replace_with);
    s = PyString_FromStringAndSize(NULL, namelen + replacelen);
    if (s == NULL)
        return NULL;

    p = PyString_AS_STRING(s);
    memcpy(p, ct->ct_name, ct->ct_name_position);
    p += ct->ct_name_position;
    memcpy(p, replace_with, replacelen);
    p += replacelen;
    memcpy(p, ct->ct_name + ct->ct_name_position,
           namelen - ct->ct_name_position);

    return s;
}

static PyObject *b_buffer(PyObject *self, PyObject *args)
{
    CDataObject *cd;
    Py_ssize_t size = -1;
    if (!PyArg_ParseTuple(args, "O!|n:buffer",
                          &CData_Type, &cd, &size))
        return NULL;

    if (cd->c_type->ct_flags & CT_POINTER) {
        if (size < 0)
            size = cd->c_type->ct_itemdescr->ct_size;
    }
    else if (cd->c_type->ct_flags & CT_ARRAY) {
        if (size < 0)
            size = get_array_length(cd) * cd->c_type->ct_itemdescr->ct_size;
    }
    else {
        PyErr_Format(PyExc_TypeError,
                     "expected a pointer or array cdata, got '%s'",
                     cd->c_type->ct_name);
        return NULL;
    }
    if (size < 0) {
        PyErr_Format(PyExc_TypeError,
                     "don't know the size pointed to by '%s'",
                     cd->c_type->ct_name);
        return NULL;
    }
    return PyBuffer_FromReadWriteMemory(cd->c_data, size);
}

static PyObject *b_get_errno(PyObject *self, PyObject *noarg)
{
    int err;
    restore_errno();
    err = errno;
    errno = 0;
    return PyInt_FromLong(err);
}

static PyObject *b_set_errno(PyObject *self, PyObject *args)
{
    int i;
    if (!PyArg_ParseTuple(args, "i:set_errno", &i))
        return NULL;
    errno = i;
    save_errno();
    errno = 0;
    Py_INCREF(Py_None);
    return Py_None;
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
    return (float)(a + b);
}
static void _testfunc5(void)
{
    errno = errno + 15;
}
static int *_testfunc6(int *x)
{
    static int y;
    y = *x - 1000;
    return &y;
}
struct _testfunc7_s { unsigned char a1; short a2; };
static short _testfunc7(struct _testfunc7_s inlined)
{
    return inlined.a1 + inlined.a2;
}
static int _testfunc9(int num, ...)
{
    va_list vargs;
    int i, total = 0;
    va_start(vargs, num);
    for (i=0; i<num; i++) {
        int value = va_arg(vargs, int);
        if (value == 0)
            value = -66666666;
        total += value;
    }
    va_end(vargs);
    return total;
}

static struct _testfunc7_s _testfunc10(int n)
{
    struct _testfunc7_s result;
    result.a1 = n;
    result.a2 = n * n;
    return result;
}

struct _testfunc11_s { int a1, a2; };
static struct _testfunc11_s _testfunc11(int n)
{
    struct _testfunc11_s result;
    result.a1 = n;
    result.a2 = n * n;
    return result;
}

struct _testfunc12_s { double a1; };
static struct _testfunc12_s _testfunc12(int n)
{
    struct _testfunc12_s result;
    result.a1 = n;
    return result;
}

struct _testfunc13_s { int a1, a2, a3; };
static struct _testfunc13_s _testfunc13(int n)
{
    struct _testfunc13_s result;
    result.a1 = n;
    result.a2 = n * n;
    result.a3 = n * n * n;
    return result;
}

struct _testfunc14_s { float a1; };
static struct _testfunc14_s _testfunc14(int n)
{
    struct _testfunc14_s result;
    result.a1 = (float)n;
    return result;
}

struct _testfunc15_s { float a1; int a2; };
static struct _testfunc15_s _testfunc15(int n)
{
    struct _testfunc15_s result;
    result.a1 = (float)n;
    result.a2 = n * n;
    return result;
}

struct _testfunc16_s { float a1, a2; };
static struct _testfunc16_s _testfunc16(int n)
{
    struct _testfunc16_s result;
    result.a1 = (float)n;
    result.a2 = -(float)n;
    return result;
}

struct _testfunc17_s { int a1; float a2; };
static struct _testfunc17_s _testfunc17(int n)
{
    struct _testfunc17_s result;
    result.a1 = n;
    result.a2 = (float)n * (float)n;
    return result;
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
    case 8: f = stderr; break;
    case 9: f = &_testfunc9; break;
    case 10: f = &_testfunc10; break;
    case 11: f = &_testfunc11; break;
    case 12: f = &_testfunc12; break;
    case 13: f = &_testfunc13; break;
    case 14: f = &_testfunc14; break;
    case 15: f = &_testfunc15; break;
    case 16: f = &_testfunc16; break;
    case 17: f = &_testfunc17; break;
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
    {"new_enum_type", b_new_enum_type, METH_VARARGS},
    {"_getfields", b__getfields, METH_O},
    {"newp", b_newp, METH_VARARGS},
    {"cast", b_cast, METH_VARARGS},
    {"callback", b_callback, METH_VARARGS},
    {"alignof", b_alignof, METH_O},
    {"sizeof", b_sizeof, METH_O},
    {"typeof", b_typeof, METH_O},
    {"offsetof", b_offsetof, METH_VARARGS},
    {"getcname", b_getcname, METH_VARARGS},
    {"buffer", b_buffer, METH_VARARGS},
    {"get_errno", b_get_errno, METH_NOARGS},
    {"set_errno", b_set_errno, METH_VARARGS},
    {"_testfunc", b__testfunc, METH_VARARGS},
    {NULL,     NULL}	/* Sentinel */
};

/************************************************************/
/* Functions used by '_cffi_N.so', the generated modules    */

static char *_cffi_to_c_char_p(PyObject *obj)
{
    if (PyString_Check(obj)) {
        return PyString_AS_STRING(obj);
    }
    if (CData_Check(obj)) {
        return ((CDataObject *)obj)->c_data;
    }
    _convert_error(obj, "char *", "compatible pointer");
    return NULL;
}

#define _cffi_to_c_PRIMITIVE(TARGETNAME, TARGET)        \
static TARGET _cffi_to_c_##TARGETNAME(PyObject *obj) {  \
    long tmp = PyInt_AsLong(obj);                       \
    if (tmp != (TARGET)tmp)                             \
        return (TARGET)_convert_overflow(obj, #TARGET); \
    return (TARGET)tmp;                                 \
}

_cffi_to_c_PRIMITIVE(signed_char,    signed char)
_cffi_to_c_PRIMITIVE(unsigned_char,  unsigned char)
_cffi_to_c_PRIMITIVE(short,          short)
_cffi_to_c_PRIMITIVE(unsigned_short, unsigned short)
#if SIZEOF_INT < SIZEOF_LONG
_cffi_to_c_PRIMITIVE(int,            int)
_cffi_to_c_PRIMITIVE(unsigned_int,   unsigned int)
#endif

#if SIZEOF_LONG < SIZEOF_LONG_LONG
static unsigned long _cffi_to_c_unsigned_long(PyObject *obj)
{
    unsigned PY_LONG_LONG value = _my_PyLong_AsUnsignedLongLong(obj, 1);
    if (value != (unsigned long)value)
        return (unsigned long)_convert_overflow(obj, "unsigned long");
    return (unsigned long)value;
}
#else
#  define _cffi_to_c_unsigned_long _cffi_to_c_unsigned_long_long
#endif

static unsigned PY_LONG_LONG _cffi_to_c_unsigned_long_long(PyObject *obj)
{
    return _my_PyLong_AsUnsignedLongLong(obj, 1);
}

static char _cffi_to_c_char(PyObject *obj)
{
    return (char)_convert_to_char(obj);
}

static PyObject *_cffi_from_c_pointer(char *ptr, CTypeDescrObject *ct)
{
    return convert_to_object((char *)&ptr, ct);
}

static char *_cffi_to_c_pointer(PyObject *obj, CTypeDescrObject *ct)
{
    char *result;
    if (convert_from_object((char *)&result, ct, obj) < 0)
        return NULL;
    return result;
}

static PyObject *_cffi_get_struct_layout(Py_ssize_t nums[])
{
    PyObject *result;
    int count = 0;
    while (nums[count] >= 0)
        count++;

    result = PyList_New(count);
    if (result == NULL)
        return NULL;

    while (--count >= 0) {
        PyObject *o = PyInt_FromSsize_t(nums[count]);
        if (o == NULL) {
            Py_DECREF(result);
            return NULL;
        }
        PyList_SET_ITEM(result, count, o);
    }
    return result;
}

static PyObject *_cffi_from_c_char(char x) {
    return PyString_FromStringAndSize(&x, 1);
}

#ifdef HAVE_WCHAR_H
static PyObject *_cffi_from_c_wchar_t(wchar_t x) {
    return _my_PyUnicode_FromWideChar(&x, 1);
}
#endif

static void *cffi_exports[] = {
    _cffi_to_c_char_p,
    _cffi_to_c_signed_char,
    _cffi_to_c_unsigned_char,
    _cffi_to_c_short,
    _cffi_to_c_unsigned_short,
#if SIZEOF_INT < SIZEOF_LONG
    _cffi_to_c_int,
    _cffi_to_c_unsigned_int,
#else
    0,
    0,
#endif
    _cffi_to_c_unsigned_long,
    _cffi_to_c_unsigned_long_long,
    _cffi_to_c_char,
    _cffi_from_c_pointer,
    _cffi_to_c_pointer,
    _cffi_get_struct_layout,
    restore_errno,
    save_errno,
    _cffi_from_c_char,
    convert_to_object,
    convert_from_object,
    convert_struct_to_owning_object,
#ifdef HAVE_WCHAR_H
    _convert_to_wchar_t,
    _cffi_from_c_wchar_t,
#else
    0,
    0,
#endif
};

/************************************************************/

void init_cffi_backend(void)
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

    m = Py_InitModule("_cffi_backend", FFIBackendMethods);
    if (m == NULL)
        return;
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
    if (PyType_Ready(&CDataIter_Type) < 0)
        return;

    v = PyCObject_FromVoidPtr((void *)cffi_exports, NULL);
    if (v == NULL || PyModule_AddObject(m, "_C_API", v) < 0)
        return;

    v = PyString_FromString("0.2.1");
    if (v == NULL || PyModule_AddObject(m, "__version__", v) < 0)
        return;

#if defined(MS_WIN32) && !defined(_WIN64)
    v = PyInt_FromLong(FFI_STDCALL);
    if (v == NULL || PyModule_AddObject(m, "FFI_STDCALL", v) < 0)
        return;
#endif
    v = PyInt_FromLong(FFI_DEFAULT_ABI);
    if (v == NULL || PyModule_AddObject(m, "FFI_DEFAULT_ABI", v) < 0)
        return;
    Py_INCREF(v);
    if (PyModule_AddObject(m, "FFI_CDECL", v) < 0)  /* win32 name */
        return;

    init_errno();
}
