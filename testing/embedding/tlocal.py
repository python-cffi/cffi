import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add1(int, int);
""", dllexport=True)

ffi.embedding_init_code(r"""
    from _tlocal_cffi import ffi
    import thread, itertools
    tloc = thread._local()
    g_seen = itertools.count()

    @ffi.def_extern()
    def add1(x, y):
        try:
            num = tloc.num
        except AttributeError:
            num = tloc.num = g_seen.next() * 1000
        return x + y + num
""")

ffi.set_source("_tlocal_cffi", """
""")

fn = ffi.compile(verbose=True)
print 'FILENAME:', fn
