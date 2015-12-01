import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add(int, int);
""", dllexport=True)

ffi.embedding_init_code("""
    from _embedding_cffi import ffi, lib

    @ffi.def_extern()
    def add(x, y):
        print "adding", x, "and", y
        return x + y
""")

ffi.set_source("libembedding_test", """
""")

ffi.compile()
