
#ifndef MS_WIN32
#  error "only GCC or Win32 are supported so far"
#endif

struct cffi_errno_s {
    int saved_errno;
    int saved_lasterror;
};

static DWORD cffi_tls_index;

static void init_errno(void)
{
    cffi_tls_index = TlsAlloc();
    if (cffi_tls_index == TLS_OUT_OF_INDEXES)
        PyErr_SetString(PyExc_WindowsError, "TlsAlloc() failed");
}

static struct cffi_errno_s *_geterrno_object(void)
{
    LPVOID p = TlsGetValue(cffi_tls_index);

    if (p == NULL) {
        p = PyMem_Malloc(sizeof(struct cffi_errno_s));
        if (p == NULL)
            return NULL;
        memset(p, 0, sizeof(struct cffi_errno_s));
        TlsSetValue(cffi_tls_index, p);
    }
    return (struct cffi_errno_s *)p;
}

static void save_errno(void)
{
    int current_err = errno;
    int current_lasterr = GetLastError();
    struct cffi_errno_s *p;

    p = _geterrno_object();
    if (p != NULL) {
        p->saved_errno = current_err;
        p->saved_lasterror = current_lasterr;
    }
    /* else: cannot report the error */
}

static void restore_errno(void)
{
    struct cffi_errno_s *p;

    p = _geterrno_object();
    if (p != NULL) {
        SetLastError(p->saved_lasterror);
        errno = p->saved_errno;
    }
    /* else: cannot report the error */
}
