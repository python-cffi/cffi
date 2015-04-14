static PyObject *FFIError;

#include "parse_c_type.c"
#include "realize_c_type.c"

typedef struct FFIObject_s FFIObject;
typedef struct LibObject_s LibObject;

static PyTypeObject FFI_Type;   /* forward */
static PyTypeObject Lib_Type;   /* forward */

#include "ffi_obj.c"
#include "lib_obj.c"


static int init_ffi_lib(PyObject *m)
{
    if (!PyType_Ready(&FFI_Type) < 0)
        return -1;
    if (!PyType_Ready(&Lib_Type) < 0)
        return -1;

    FFIError = PyErr_NewException("ffi.error", NULL, NULL);
    if (FFIError == NULL)
        return -1;
    if (PyDict_SetItemString(FFI_Type.tp_dict, "error", FFIError) < 0)
        return -1;
    if (PyDict_SetItemString(FFI_Type.tp_dict, "CType",
                             (PyObject *)&CTypeDescr_Type) < 0)
        return -1;

    Py_INCREF(&FFI_Type);
    if (PyModule_AddObject(m, "FFI", (PyObject *)&FFI_Type) < 0)
        return -1;
    Py_INCREF(&Lib_Type);
    if (PyModule_AddObject(m, "Lib", (PyObject *)&Lib_Type) < 0)
        return -1;

    return 0;
}

static int _cffi_init_module(char *module_name,
                             const struct _cffi_type_context_s *ctx)
{
    PyObject *m = Py_InitModule(module_name, NULL);
    if (m == NULL)
        return -1;

    FFIObject *ffi = ffi_internal_new(ctx);
    if (ffi == NULL || PyModule_AddObject(m, "ffi", (PyObject *)ffi) < 0)
        return -1;

    LibObject *lib = lib_internal_new(ctx, module_name);
    if (lib == NULL || PyModule_AddObject(m, "lib", (PyObject *)lib) < 0)
        return -1;

    return 0;
}
