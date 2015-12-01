
/***** Support code for embedding *****/

#ifdef PYPY_VERSION
#  error PyPy!
#endif

#if defined(_MSC_VER)
#  define CFFI_DLLEXPORT  __declspec(dllexport)
#elif defined(__GNUC__)
#  define CFFI_DLLEXPORT  __attribute__ ((visibility("default")))
#else
#  define CFFI_DLLEXPORT  /* nothing */
#endif

#ifdef WITH_THREAD
#  include <pthread.h>   // XXX Windows
static pthread_once_t _cffi_init_once = PTHREAD_ONCE_INIT;
#endif

PyMODINIT_FUNC _CFFI_PYTHON_STARTUP_FUNC(void);   /* forward */

static void _cffi_call_python_failed(struct _cffi_externpy_s *externpy,
                                     char *args)
{
    int saved_errno = errno;
    fprintf(stderr, "function %s() called, but initialization code failed.  "
                    "Returning 0.\n", externpy->name);
    memset(args, 0, externpy->size_of_result);
    errno = saved_errno;
}

static void _cffi_start_python(void)
{
    Py_Initialize();
    if (PyErr_Occurred())
        goto error;

    (void)_CFFI_PYTHON_STARTUP_FUNC();
    if (PyErr_Occurred())
        goto error;

    if (PyRun_SimpleString(_CFFI_PYTHON_STARTUP_CODE) < 0)
        goto error;

    return;

 error:;
    {
        /* Print as much information as potentially useful.
           Debugging load-time failures with embedding is not fun
        */
        PyObject *exception, *v, *tb, *f, *modules, *mod;
        PyErr_Fetch(&exception, &v, &tb);
        if (exception != NULL) {
            PyErr_NormalizeException(&exception, &v, &tb);
            PyErr_Display(exception, v, tb);
        }
        Py_XDECREF(exception);
        Py_XDECREF(v);
        Py_XDECREF(tb);

        f = PySys_GetObject("stderr");
        if (f != NULL && f != Py_None) {
            PyFile_WriteString("\ncffi version: 1.3.1", f);
            PyFile_WriteString("\n_cffi_backend module: ", f);
            modules = PyImport_GetModuleDict();
            mod = PyDict_GetItemString(modules, "_cffi_backend");
            if (mod == NULL) {
                PyFile_WriteString("not loaded", f);
            }
            else {
                v = PyObject_GetAttrString(mod, "__file__");
                PyFile_WriteObject(v, f, 0);
                Py_XDECREF(v);
            }
            PyFile_WriteString("\nsys.path: ", f);
            PyFile_WriteObject(PySys_GetObject("path"), f, 0);
            PyFile_WriteString("\n\n", f);
        }
    }
    _cffi_exports[_CFFI_CPIDX] = &_cffi_call_python_failed;
}

/* The CFFI_START_PYTHON() macro makes sure Python is initialized
   and our cffi module is set up.  It can be called manually from
   the user C code, and it is called automatically before any
   dll-exported ``extern "Python"`` function is invoked.
*/
#define CFFI_START_PYTHON()  do {                       \
    pthread_once(&_cffi_init_once, _cffi_start_python); \
} while (0)
