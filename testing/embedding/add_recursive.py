import cffi

ffi = cffi.FFI()

ffi.cdef("""
    int (*my_callback)(int);
    extern "Python" int add_rec(int, int);
""", dllexport=True)

ffi.embedding_init_code(r"""
    from _add_recursive_cffi import ffi, lib
    import sys
    print("preparing REC")
    sys.stdout.flush()

    @ffi.def_extern()
    def add_rec(x, y):
        print("adding %d and %d" % (x, y))
        sys.stdout.flush()
        return x + y

    x = lib.my_callback(400)
    print('<<< %d >>>' % (x,))
""")

ffi.set_source("_add_recursive_cffi", """
int (*my_callback)(int);
""")

fn = ffi.compile(verbose=True)
print('FILENAME: %s' % (fn,))
