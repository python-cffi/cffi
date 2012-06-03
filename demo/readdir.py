# A Linux-only demo
#
from ffi import FFI


ffi = FFI()
ffi.cdef("""

    typedef void DIR;
    typedef long ino_t;
    typedef long off_t;

    struct dirent {
        ino_t          d_ino;       
        off_t          d_off;       
        unsigned short d_reclen;    
        unsigned char  d_type;      
        char           d_name[256]; 
    };

    int readdir_r(DIR *dirp, struct dirent *entry, struct dirent **result);
    int openat(int dirfd, const char *pathname, int flags);
    DIR *fdopendir(int fd);
    int closedir(DIR *dirp);

""")



def walk(basefd, path):
    print '{', path
    dirfd = ffi.C.openat(basefd, path, 0)
    if dirfd < 0:
        # error in openat()
        return
    dir = ffi.C.fdopendir(dirfd)
    dirent = ffi.new("struct dirent")
    result = ffi.new("struct dirent *")
    while True:
        if ffi.C.readdir_r(dir, dirent, result):
            # error in readdir_r()
            break
        if result[0] is None:
            break
        name = str(dirent.d_name)
        print '%3d %s' % (dirent.d_type, name)
        if dirent.d_type == 4 and name != '.' and name != '..':
            walk(dirfd, name)
    ffi.C.closedir(dir)
    print '}'


walk(-1, "/tmp")
