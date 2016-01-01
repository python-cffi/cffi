import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" int add2(int, int, int);
""", dllexport=True)

ffi.embedding_init_code(r"""
    import sys
    sys.stdout.write("prepADD2\n")

    @ffi.def_extern()
    def add2(x, y, z):
        sys.stdout.write("adding %d and %d and %d\n" % (x, y, z))
        return x + y + z
""")

ffi.set_source("_add2_cffi", """
""")

ffi.compile()
