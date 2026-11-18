import bsdopendirtype_build

from cffi import FFI

ffi = FFI()

# ========== This is a demo of ffi.include() ==========
ffi.include(bsdopendirtype_build.ffi)

ffi.cdef("""
    int readdir_r(DIR *dirp, struct dirent *entry, struct dirent **result);
""")

ffi.set_source("_recopendirtype", """
    #include <sys/types.h>
    #include <dirent.h>
""")

if __name__ == '__main__':
    ffi.compile()
