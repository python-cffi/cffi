from cffi import FFI

ffi = FFI()
ffi.cdef("""
    typedef ... DIR;
    struct dirent {
        unsigned char d_type;   /* type of file */
        char d_name[];          /* filename */
        ...;
    };
    DIR *opendir(const char *name);
    int closedir(DIR *dirp);
    struct dirent *readdir(DIR *dirp);
    static const int DT_BLK, DT_CHR, DT_DIR, DT_FIFO, DT_LNK, DT_REG, DT_SOCK;
""")
lib = ffi.verify("""
    #include <sys/types.h>
    #include <dirent.h>
""")


def _posix_error():
    raise OSError(ffi.errno, os.strerror(ffi.errno))

_dtype_to_smode = {
    lib.DT_BLK:  0o060000,
    lib.DT_CHR:  0o020000,
    lib.DT_DIR:  0o040000,
    lib.DT_FIFO: 0o010000,
    lib.DT_LNK:  0o120000,
    lib.DT_REG:  0o100000,
    lib.DT_SOCK: 0o140000,
}

def opendir(dir):
    if len(dir) == 0:
        dir = '.'
    dirname = dir
    if not dirname.endswith('/'):
        dirname += '/'
    dirp = lib.opendir(dir)
    if dirp == ffi.NULL:
        raise _posix_error()
    try:
        while True:
            ffi.errno = 0
            dirent = lib.readdir(dirp)
            if dirent == ffi.NULL:
                if ffi.errno != 0:
                    raise _posix_error()
                return
            name = ffi.string(dirent.d_name)
            if name == '.' or name == '..':
                continue
            name = dirname + name
            try:
                smode = _dtype_to_smode[dirent.d_type]
            except KeyError:
                smode = os.lstat(name).st_mode
            yield name, smode
    finally:
        lib.closedir(dirp)
