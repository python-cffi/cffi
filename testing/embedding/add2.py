import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add2(int, int, int);
""", dllexport=True)

ffi.embedding_init_code("""
    print("preparing ADD2")

    @ffi.def_extern()
    def add2(x, y, z):
        print "adding", x, "and", y, "and", z
        return x + y + z
""")

ffi.set_source("_add2_cffi", """
""")

ffi.compile()
