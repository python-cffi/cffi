import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add1(int, int);
""", dllexport=True)

ffi.embedding_init_code("""
    print("preparing")

    int(ord("A"))    # check that built-ins are there

    @ffi.def_extern()
    def add1(x, y):
        print "adding", x, "and", y
        return x + y
""")

ffi.set_source("_add1_cffi", """
""")

ffi.compile()
