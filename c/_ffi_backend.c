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

#define CT_PRIMITIVE    (CT_PRIMITIVE_SIGNED |          \
                         CT_PRIMITIVE_UNSIGNED |        \
                         CT_PRIMITIVE_CHAR |            \
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


static CTypeDescrObject *
ctypedescr_new(const char *name)
{
    int name_size = strlen(name) + 1;
    CTypeDescrObject *ct = PyObject_GC_NewVar(CTypeDescrObject,
                                              &CTypeDescr_Type,
                                              name_size);
    if (ct == NULL)
        return NULL;

    memcpy(ct->ct_name, name, sizeof(char) * name_size);
    ct->ct_itemdescr = NULL;
    ct->ct_fields = NULL;
    PyObject_GC_Track(ct);
    return ct;
}

static PyObject *
ctypedescr_repr(CTypeDescrObject *ct)
{
    return PyString_FromFormat("<ctypedescr '%s'>", ct->ct_name);
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

static PyObject *load_library(PyObject *self, PyObject *args)
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

static PyObject *nonstandard_integer_types(PyObject *self, PyObject *noarg)
{
    static const int UNSIGNED = 0x1000;
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

static PyObject *new_primitive_type(PyObject *self, PyObject *args)
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

    if (!PyArg_ParseTuple(args, "Os", &ffi, &name))
        return NULL;

    for (ptypes=types; ; ptypes++) {
        if (ptypes->name == NULL) {
            PyErr_SetString(PyExc_KeyError, name);
            return NULL;
        }
        if (strcmp(name, ptypes->name) == 0)
            break;
    }

    td = ctypedescr_new(ptypes->name);
    if (td == NULL)
        return NULL;

    td->ct_itemdescr = NULL;
    td->ct_fields = NULL;
    td->ct_size = ptypes->size;
    td->ct_flags = ptypes->flags;
    td->ct_name_position = strlen(td->ct_name);
    return (PyObject *)td;
}

static PyMethodDef FFIBackendMethods[] = {
    {"nonstandard_integer_types", nonstandard_integer_types, METH_NOARGS},
    {"load_library", load_library, METH_VARARGS},
    {"new_primitive_type", new_primitive_type, METH_VARARGS},
    {NULL,     NULL}	/* Sentinel */
};

void init_ffi_backend(void)
{
    PyObject* m;
    m = Py_InitModule("_ffi_backend", FFIBackendMethods);
    if (PyType_Ready(&dl_type) < 0)
        return;
    if (PyType_Ready(&CTypeDescr_Type) < 0)
        return;
}
