
/***** Support code for embedding *****/

#if defined(_MSC_VER)
#  define CFFI_DLLEXPORT  __declspec(dllexport)
#elif defined(__GNUC__)
#  define CFFI_DLLEXPORT  __attribute__ ((visibility("default")))
#else
#  define CFFI_DLLEXPORT  /* nothing */
#endif

#ifdef WITH_THREAD
# ifndef _MSC_VER
#  include <pthread.h>
   static pthread_mutex_t _cffi_embed_startup_lock;
# else
   static CRITICAL_SECTION _cffi_embed_startup_lock;
# endif
  static char _cffi_embed_startup_lock_ready = 0;
#endif

static void _cffi_init_embed_lock(void)
{
#ifdef WITH_THREAD
    if (!_cffi_embed_startup_lock_ready) {
# ifndef _MSC_VER
        pthread_mutexattr_t attr;
        pthread_mutexattr_init(&attr);
        pthread_mutexattr_settype(&attr, PTHREAD_MUTEX_RECURSIVE);
        pthread_mutex_init(&_cffi_embed_startup_lock, &attr);
# else
        InitializeCriticalSection(&_cffi_embed_startup_lock);
# endif
        _cffi_embed_startup_lock_ready = 1;
    }
#endif
}

#ifndef _MSC_VER
   /* --- Assuming a GCC not infinitely old --- */
# define compare_and_swap(l,o,n)  __sync_bool_compare_and_swap(l,o,n)
# define write_barrier()          __sync_synchronize()
#else
   /* --- Windows threads version --- */
# define compare_and_swap(l,o,n)  InterlockedCompareExchangePointer(l,n,o)
# define write_barrier()          InterlockedCompareExchange(&_cffi_dummy,0,0)
static volatie LONG _cffi_dummy;
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

#define _cffi_call_python_org  _cffi_exports[_CFFI_CPIDX]

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

    /* Call the initxxx() function from the present module.  It will
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

#ifdef WITH_THREAD

static void _cffi_carefully_make_gil(void)
{
    /* This initializes the GIL.  It can be called completely
       concurrently from unrelated threads.

       PyEval_InitThreads() must not be called concurrently at all.
       So we use a global variable as a simple spin lock.  This global
       variable must be from 'libpythonX.Y.so', not from this
       cffi-based extension module, because it must be shared from
       different cffi-based extension modules.  We choose
       PyEllipsis_Type.tp_dealloc as a completely arbitrary,
       never-used word for this lock.  (Yes, I know it's really
       obscure.)
    */
    void *volatile *lock = (void *volatile *)&PyEllipsis_Type.tp_dealloc;

    while (1) {    /* spin loop */
        void *current = *lock;
        if (current == NULL) {
            if (compare_and_swap(lock, NULL, (void *)42))
                break;
        }
        else {
            assert(current == (void *)42);
            /* should ideally do a spin loop instruction here, but
               hard to do it portably and doesn't really matter I
               think: PyEval_InitThreads() should be very fast, and
               this is only run at start-up anyway. */
        }
    }

    if (!PyEval_ThreadsInitialized()) {
        PyEval_InitThreads();    /* makes the GIL */
        PyEval_ReleaseLock();    /* then release it */
    }

    _cffi_init_embed_lock();

    /* else: we already have the GIL, but we still needed to do the
       spinlock dance to make sure that we see it as fully ready */

    /* release the lock */
    while (!compare_and_swap(lock, (void *)42, NULL))
        ;

}

static void _cffi_acquire_reentrant_mutex_and_gil(void)
{
    _cffi_carefully_make_gil();
#ifndef _MSC_VER
    pthread_mutex_lock(&_cffi_embed_startup_lock);
#else
    EnterCriticalSection(&_cffi_embed_startup_lock);
#endif
    PyEval_AcquireLock();
}

static void _cffi_release_reentrant_mutex_and_gil(void)
{
    PyEval_ReleaseLock();
#ifndef _MSC_VER
    pthread_mutex_unlock(&_cffi_embed_startup_lock);
#else
    LeaveCriticalSection(&_cffi_embed_startup_lock);
#endif
}

#else   /* !WITH_THREAD */
static void _cffi_acquire_reentrant_mutex_and_gil(void) { }
static void _cffi_release_reentrant_mutex_and_gil(void) { }
#define write_barrier()    (void)0
#endif


/**********  end CPython-specific section  **********/

#else

/**********  PyPy-specific section  **********/

PyMODINIT_FUNC _CFFI_PYTHON_STARTUP_FUNC(const void *[]);   /* forward */

extern int pypy_init_embedded_cffi_module(void(const void *[]));

static void _cffi_acquire_reentrant_mutex_and_gil(void)
{
    static volatile void *lock = NULL;

    while (!compare_and_swap(lock, NULL, (void *)1)) {
        /* should ideally do a spin loop instruction here, but
           hard to do it portably and doesn't really matter I
           think: PyEval_InitThreads() should be very fast, and
           this is only run at start-up anyway. */
    }

    _cffi_init_embed_lock();

    while (!compare_and_swap(lock, (void *)1, NULL))
        ;

#ifndef _MSC_VER
    pthread_mutex_lock(&_cffi_embed_startup_lock);
#else
    EnterCriticalSection(&_cffi_embed_startup_lock);
#endif
}

static void _cffi_release_reentrant_mutex_and_gil(void)
{
#ifndef _MSC_VER
    pthread_mutex_unlock(&_cffi_embed_startup_lock);
#else
    LeaveCriticalSection(&_cffi_embed_startup_lock);
#endif
}

static int _cffi_initialize_python(void)
{
    return pypy_init_embedded_cffi_module(0xB011, _CFFI_PYTHON_STARTUP_FUNC,
                                          _CFFI_PYTHON_STARTUP_CODE);
}

/**********  end PyPy-specific section  **********/

#endif


#ifdef __GNUC__
__attribute__((noinline))
#endif
static _cffi_call_python_fnptr _cffi_start_python(void)
{
    /* Delicate logic to initialize Python.  This function can be
       called multiple times concurrently, e.g. when the process calls
       its first ``extern "Python"`` functions in multiple threads at
       once.  It can also be called recursively, in which case we must
       ignore it.  We also have to consider what occurs if several
       different cffi-based extensions reach this code in parallel
       threads---it is a different copy of the code, then, and we
       can't have any shared global variable unless it comes from
       'libpythonX.Y.so'.

       Idea:

       * _cffi_carefully_make_gil(): "carefully" call
         PyEval_InitThreads().  This can be called before
         Py_Initialize().

       * then we use a custom lock to make sure that a call to this
         cffi-based extension will wait if another call to the same
         extension is running the initialization in another thread.
         It is reentrant, so that a recursive call will not block, but
         only one from a different thread.

       * then we grab the GIL and call Py_Initialize(), which will
         initialize Python or do nothing if already initialized.  We
         know that concurrent calls to Py_Initialize() should not be
         possible, even from different cffi-based extension, because
         we have the GIL.

       * do the rest of the specific initialization, which may
         temporarily release the GIL but not the custom lock.
         Only release the custom lock when we are done.
    */
    static char called = 0;

    _cffi_carefully_make_gil();
    _cffi_acquire_reentrant_mutex();

    /* Here the GIL exists, but we don't have it.  We're only protected
       from concurrency by the reentrant mutex. */
    if (!called) {
        called = 1;  /* invoke _cffi_initialize_python() only once,
                        but don't set '_cffi_call_python' right now,
                        otherwise concurrent threads won't call
                        this function at all (we need them to wait) */
        if (_cffi_initialize_python() == 0) {
            /* now initialization is finished.  Switch to the fast-path. */

            /* We would like nobody to see the new value of
               '_cffi_call_python' without also seeing the rest of the
               data initialized.  However, this is not possible.  But
               the new value of '_cffi_call_python' is the function
               'cffi_call_python()' from _cffi_backend.  We can put a
               write barrier here, and a corresponding read barrier at
               the start of cffi_call_python().  This ensures that
               after that read barrier, we see everything done here
               before the write barrier.
            */
            write_barrier();

            assert(_cffi_call_python_org != NULL);
            _cffi_call_python = (_cffi_call_python_fnptr)_cffi_call_python_org;
        }
        else {
            /* initialization failed.  Reset this to NULL, even if it was
               already set to some other value.  Future calls to
               _cffi_start_python() are still forced to occur, and will
               always return NULL from now on. */
            _cffi_call_python_org = NULL;
        }
    }

    _cffi_release_reentrant_mutex();

    return (_cffi_call_python_fnptr)_cffi_call_python_org;
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

#undef compare_and_swap
#undef write_barrier


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
