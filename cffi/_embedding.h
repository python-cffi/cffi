
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

#if defined(WITH_THREAD) && !defined(_MSC_VER)
# include <pthread.h>
static pthread_mutex_t _cffi_embed_startup_lock;
static void _cffi_embed_startup_lock_create(void) {
    pthread_mutexattr_t attr;
    pthread_mutexattr_init(&attr);
    pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE);
    pthread_mutex_init(&_cffi_embed_startup_lock, &attr);
}
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

static void _cffi_initialize_python(void)
{
    /* Initialize this to the "failed" function above.  It will be
       replaced with the real function from cffi when Python is
       more initialized, _cffi_backend is imported, and the present
       .dll/.so is set up as a CPython C extension module.
    */
    _cffi_exports[_CFFI_CPIDX] = (void *)(uintptr_t)&_cffi_call_python_failed;

    /* XXX use initsigs=0, which "skips initialization registration of
       signal handlers, which might be useful when Python is
       embedded" according to the Python docs.  But review and think
       if it should be a user-controllable setting.
    */
    Py_InitializeEx(0);
    if (PyErr_Occurred())
        goto error;

    /* Call the initxxx() function from the same module.  It will
       create and initialize us as a CPython extension module, instead
       of letting the startup Python code do it---it might reimport
       the same .dll/.so and get maybe confused on some platforms.
       It might also have troubles locating the .dll/.so again for all
       I know.
    */
    (void)_CFFI_PYTHON_STARTUP_FUNC();
    if (PyErr_Occurred())
        goto error;

    /* Now run the Python code provided to ffi.embedding_init_code().
     */
    if (PyRun_SimpleString(_CFFI_PYTHON_STARTUP_CODE) < 0)
        goto error;

    /* Done!  Now if we've been called from CFFI_START_PYTHON() in an
       ``extern "Python"``, we can only hope that the Python code
       correctly set some @ffi.def_extern() function.  Otherwise, the
       reference is still missing and we'll print an error.
     */
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

        f = PySys_GetObject((char *)"stderr");
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
            PyFile_WriteObject(PySys_GetObject((char *)"path"), f, 0);
            PyFile_WriteString("\n\n", f);
        }
    }
}

static char _cffi_python_started = 0;

#ifdef __GNUC__
__attribute__((noinline))
#endif
static void _cffi_start_python(void)
{
    /* This function can be called multiple times concurrently if the
       process calls its first ``extern "Python"`` functions in
       multiple threads at once.  Additionally, it can be called
       recursively.
    */
    static char called = 0;

#ifdef WITH_THREAD

# ifndef _MSC_VER
    /* --- Posix threads version --- */

    /* pthread_once() cannot be used to call directly
       _cffi_initialize_python(), because it is not reentrant: it
       deadlocks. */
    static pthread_once_t once_control = PTHREAD_ONCE_INIT;
    pthread_once(&once_control, &_cffi_embed_startup_lock_create);
#define lock_enter()  pthread_mutex_lock(&_cffi_embed_startup_lock)
#define lock_leave()  pthread_mutex_unlock(&_cffi_embed_startup_lock)

# else
    /* --- Windows threads version --- */
    static volatile LONG spinloop = 0;
    static CRITICAL_SECTION lock;
    /* This delicate loop is here only to initialize the
       critical section object, which we will use below */
 retry:
    switch (InterlockedCompareExchange(&spinloop, 1, 0)) {
    case 0:
        /* the 'spinloop' value was changed from 0 to 1 */
        InitializeCriticalSection(&lock);
        InterlockedCompareExchange(&spinloop, 2, 1);
        break;
    case 1:
        /* 'spinloop' was already 1, another thread is busy
           initializing the lock... try again, it should be very
           fast */
        _mm_pause();
        goto retry;
    default:
        /* 'spinloop' is now 2, done */
        break;
    }
#define lock_enter()  EnterCriticalSection(&lock)
#define lock_leave()  LeaveCriticalSection(&lock)

# endif
#else
    /* !WITH_THREAD --- no thread at all.  We assume there are no
       concurrently issues in this case. */
#define lock_enter()  (void)0
#define lock_leave()  (void)0
#endif

    /* General code follows.  Uses reentrant locks, so a recursive
       call to _cffi_start_python() will not block and do nothing. */
    lock_enter();
    if (!called) {
        called = 1;  /* invoke _cffi_initialize_python() only once,
                        but don't set _cffi_python_started right now,
                        otherwise concurrent threads won't call
                        _cffi_start_python() at all */
        _cffi_initialize_python();
        _cffi_python_started = 1;   /* do this only when it's done */
    }
    lock_leave();

#undef lock_enter
#undef lock_leave
}


/* The CFFI_START_PYTHON() macro makes sure Python is initialized
   and our cffi module is set up.  It can be called manually from
   the user C code, and it is called automatically from any
   dll-exported ``extern "Python"`` function.
*/
#define CFFI_START_PYTHON()  do {               \
    if (!_cffi_python_started)                  \
        _cffi_start_python();                   \
} while (0)
