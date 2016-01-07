import cffi

ffi = cffi.FFI()

ffi.cdef("""
    extern "Python" {
        int add(int, int);
    }
""", dllexport=True)

ffi.embedding_init_code("""
    from _embedding_cffi import ffi
    print "preparing"   # printed once

    @ffi.def_extern()
    def add(x, y):
        print "adding", x, "and", y
        return x + y
""")

ffi.set_source("_embedding_cffi", """
""")

#ffi.compile()   -- should be fixed to do the right thing

ffi.emit_c_code('_embedding_cffi.c')
# then call the compiler manually with the proper options, like:
#    gcc -shared -fPIC _embedding_cffi.c -o _embedding_cffi.so -lpython2.7
#        -I/usr/include/python2.7
