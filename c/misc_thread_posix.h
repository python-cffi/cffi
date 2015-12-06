/*
  Logic for a better replacement of PyGILState_Ensure().

  This version is ready to handle the case of a non-Python-started
  thread in which we do a large number of calls to CFFI callbacks.  If
  we were to rely on PyGILState_Ensure() for that, we would constantly
  be creating and destroying PyThreadStates---it is slow, and
  PyThreadState_Delete() will actually walk the list of all thread
  states, making it O(n). :-(

  This version only creates one PyThreadState object the first time we
  see a given thread, and keep it alive until the thread is really
  shut down, using a destructor on the tls key.
*/

#ifdef WITH_THREAD
#include <pthread.h>


static pthread_key_t cffi_tls_key;

struct cffi_tls_s {
    /* The locally-made thread state.  This is only non-null in case
       we build the thread state here.  It remains null if this thread
       had already a thread state provided by CPython. */
    PyThreadState *local_thread_state;

    /* The saved errno.  If the C compiler supports '__thread', then
       we use that instead; this value is not used at all in this case. */
    int saved_errno;
};

static void _tls_destructor(void *p)
{
    struct cffi_tls_s *tls = (struct cffi_tls_s *)p;

    if (tls->local_thread_state != NULL) {
        /* We need to re-acquire the GIL temporarily to free the
           thread state.  I hope it is not a problem to do it in
           a thread-local destructor.
        */
        PyEval_RestoreThread(tls->local_thread_state);
        PyThreadState_DeleteCurrent();
    }
    free(tls);
}

static void init_cffi_tls(void)
{
    if (pthread_key_create(&cffi_tls_key, _tls_destructor) != 0)
        PyErr_SetString(PyExc_OSError, "pthread_key_create() failed");
}

static struct cffi_tls_s *_make_cffi_tls(void)
{
    void *p = calloc(1, sizeof(struct cffi_tls_s));
    if (p == NULL)
        return NULL;
    if (pthread_setspecific(cffi_tls_key, p) != 0) {
        free(p);
        return NULL;
    }
    return p;
}

static struct cffi_tls_s *get_cffi_tls(void)
{
    void *p = pthread_getspecific(cffi_tls_key);
    if (p == NULL)
        p = _make_cffi_tls();
    return (struct cffi_tls_s *)p;
}


/* USE__THREAD is defined by setup.py if it finds that it is
   syntactically valid to use "__thread" with this C compiler. */
#ifdef USE__THREAD

static __thread int cffi_saved_errno = 0;
static void save_errno(void) { cffi_saved_errno = errno; }
static void restore_errno(void) { errno = cffi_saved_errno; }

#else

static void save_errno(void)
{
    int saved = errno;
    struct cffi_tls_s *tls = get_cffi_tls();
    if (tls != NULL)
        tls->saved_errno = saved;
}

static void restore_errno(void)
{
    struct cffi_tls_s *tls = get_cffi_tls();
    if (tls != NULL)
        errno = tls->saved_errno;
}

#endif


static PyGILState_STATE gil_ensure(void)
{
    /* Called at the start of a callback.  Replacement for
       PyGILState_Ensure().
    */
    PyGILState_STATE result;
    struct cffi_tls_s tls;
    PyThreadState *ts = PyGILState_GetThisThreadState();

    if (ts != NULL) {
        ts->gilstate_counter++;
        if (ts != _PyThreadState_Current) {
            /* common case: 'ts' is our non-current thread state and
               we have to make it current and acquire the GIL */
            PyEval_RestoreThread(ts);
            return PyGILState_UNLOCKED;
        }
        else {
            return PyGILState_LOCKED;
        }
    }
    else {
        /* no thread state here so far. */
        result = PyGILState_Ensure();
        assert(result == PyGILState_UNLOCKED);

        ts = PyGILState_GetThisThreadState();
        assert(ts != NULL);
        assert(ts == _PyThreadState_Current);
        assert(ts->gilstate_counter >= 1);

        /* Save the now-current thread state inside our 'local_thread_state'
           field, to be removed at thread shutdown */
        tls = get_cffi_tls();
        if (tls != NULL) {
            tls->local_thread_state = ts;
            ts->gilstate_counter++;
        }

        return result;
    }
}

static void gil_release(PyGILState_STATE oldstate)
{
    PyGILState_Release(oldstate);
}


#else   /* !WITH_THREAD */

static int cffi_saved_errno = 0;
static void save_errno(void) { cffi_saved_errno = errno; }
static void restore_errno(void) { errno = cffi_saved_errno; }

#endif  /* !WITH_THREAD */


#define save_errno_only      save_errno
#define restore_errno_only   restore_errno
