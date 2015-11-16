import cffi

ffi = cffi.FFI()

ffi.cdef("""
    int add(int x, int y);
    CFFI_CALL_PYTHON long mangle(int);
""")

ffi.set_source("_cdef_call_python_cffi", """

    static long mangle(int);

    static int add(int x, int y)
    {
        return mangle(x) + mangle(y);
    }
""")

ffi.compile()


from _cdef_call_python_cffi import ffi, lib

@ffi.call_python("mangle")    # optional argument, default to func.__name__
def mangle(x):
    return x * x

assert lib.add(40, 2) == 1604
