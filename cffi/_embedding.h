
/***** Support code for embedding *****/

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

/* There are two global variables of type _cffi_call_python_fnptr:

   * _cffi_call_python, which we declare just below, is the one called
     by ``extern "Python"`` implementations.

   * _cffi_call_python_org, which on CPython is actually part of the
     _cffi_exports[] array, is the function pointer copied from
     _cffi_backend.

   After initialization is complete, both are equal.  However, the
   first one remains equal to &_cffi_start_and_call_python until the
   very end of initialization, when we are (or should be) sure that
   concurrent threads also see a completely initialized world, and
   only then is it changed.
*/
#undef _cffi_call_python
typedef void (*_cffi_call_python_fnptr)(struct _cffi_externpy_s *, char *);
static void _cffi_start_and_call_python(struct _cffi_externpy_s *, char *);
static _cffi_call_python_fnptr _cffi_call_python = &_cffi_start_and_call_python;


/**********  CPython-specific section  **********/
#ifndef PYPY_VERSION

#define _cffi_call_python_org                                   \
    ((_cffi_call_python_fnptr)_cffi_exports[_CFFI_CPIDX])

PyMODINIT_FUNC _CFFI_PYTHON_STARTUP_FUNC(void);   /* forward */

static int _cffi_initialize_python(void)
{
    /* This initializes Python, imports _cffi_backend, and then the
       present .dll/.so is set up as a CPython C extension module.
    */

    /* XXX use initsigs=0, which "skips initialization registration of
       signal handlers, which might be useful when Python is
       embedded" according to the Python docs.  But review and think
       if it should be a user-controllable setting.

       XXX we should also give a way to write errors to a buffer
       instead of to stderr.
    */
    Py_InitializeEx(0);

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

    /* Done!  Now if we've been called from
       _cffi_start_and_call_python() in an ``extern "Python"``, we can
       only hope that the Python code did correctly set up the
       corresponding @ffi.def_extern() function.  Otherwise, the
       general logic of ``extern "Python"`` functions (inside the
       _cffi_backend module) will find that the reference is still
       missing and print an error.
     */
    return 0;

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
        return -1;
    }
}

/**********  end CPython-specific section  **********/

#else

/**********  PyPy-specific section  **********/

PyMODINIT_FUNC _CFFI_PYTHON_STARTUP_FUNC(const void *[]);   /* forward */

static int _cffi_initialize_python(void)
{
    rpython_startup_code();
    pypy_setup_home(...);
}

/**********  end PyPy-specific section  **********/

#endif


#ifdef __GNUC__
__attribute__((noinline))
#endif
static _cffi_call_python_fnptr _cffi_start_python(void)
{
    /* This function can be called multiple times concurrently,
       e.g. when the process calls its first ``extern "Python"``
       functions in multiple threads at once.  Additionally, it can be
       called recursively.
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
#define lock_write_barrier()   __sync_synchronize()

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
# ifdef _WIN64
        YieldProcessor();
# else
        __asm pause;
# endif
        goto retry;
    default:
        /* 'spinloop' is now 2, done */
        break;
    }
#define lock_enter()  EnterCriticalSection(&lock)
#define lock_leave()  LeaveCriticalSection(&lock)
#define lock_write_barrier()   InterlockedCompareExchange(&spinloop, 2, 2)

# endif
#else
    /* !WITH_THREAD --- no thread at all.  We assume there are no
       concurrently issues in this case. */
#define lock_enter()  (void)0
#define lock_leave()  (void)0
#define lock_write_barrier()   (void)0
#endif

    /* General code follows.  Uses reentrant locks, so a recursive
       call to _cffi_start_python() will not block and do nothing. */
    lock_enter();
    if (!called) {
        called = 1;  /* invoke _cffi_initialize_python() only once,
                        but don't set '_cffi_call_python' right now,
                        otherwise concurrent threads won't call
                        _cffi_start_python() at all */
        if (_cffi_initialize_python() == 0) {
            lock_write_barrier();
            assert(_cffi_call_python_org != NULL);
            _cffi_call_python = _cffi_call_python_org;
        }
    }
    lock_leave();

    return _cffi_call_python_org;

#undef lock_enter
#undef lock_leave
}


static
void _cffi_start_and_call_python(struct _cffi_externpy_s *externpy, char *args)
{
    _cffi_call_python_fnptr fnptr;
    int current_err = errno;
#ifdef _MSC_VER
    int current_lasterr = GetLastError();
#endif
    fnptr = _cffi_start_python();
    if (fnptr == NULL) {
        fprintf(stderr, "function %s() called, but initialization code "
                        "failed.  Returning 0.\n", externpy->name);
        memset(args, 0, externpy->size_of_result);
    }
#ifdef _MSC_VER
    SetLastError(current_lasterr);
#endif
    errno = current_err;

    if (fnptr != NULL)
        fnptr(externpy, args);
}


/* The cffi_start_python() function makes sure Python is initialized
   and our cffi module is set up.  It can be called manually from the
   user C code.  The same effect is obtained automatically from any
   dll-exported ``extern "Python"`` function.  This function returns
   -1 if initialization failed, 0 if all is OK.  */
_CFFI_UNUSED_FN
static int cffi_start_python(void)
{
    if (_cffi_call_python == &_cffi_start_and_call_python) {
        if (_cffi_start_python() == NULL)
            return -1;
    }
    return 0;
}
