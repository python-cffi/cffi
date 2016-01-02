import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add1(int, int);
""", dllexport=True)

ffi.embedding_init_code(r"""
    @ffi.def_extern()
    def add1(x, y):
        return x + y
""")

ffi.set_source("_perf_cffi", """
""")

ffi.compile(verbose=True)
