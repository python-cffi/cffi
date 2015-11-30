import cffi

ffi = cffi.FFI()

ffi.export_cdef("""
    extern "Python" int add(int, int);
""", """
    from _embedding_cffi import ffi, lib

    @ffi.def_extern()
    def add(x, y):
        print "adding", x, "and", y
        return x + y
""")

ffi.set_source("libembedding_test", """
""")

ffi.compile()
