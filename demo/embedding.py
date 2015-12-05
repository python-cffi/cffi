import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add(int, int);
""", dllexport=True)

ffi.embedding_init_code("""
    print "preparing"

    @ffi.def_extern()
    def add(x, y):
        print "adding", x, "and", y
        return x + y
""")

ffi.set_source("_embedding_cffi", """
""")

ffi.compile()
