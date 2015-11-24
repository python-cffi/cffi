# A Linux-only demo, using set_source() instead of hard-coding the exact layouts
#
import sys

if not sys.platform.startswith('linux'):
    raise Exception("Linux-only demo")

# If the build script was run immediately before this script, the cffi module
# ends up in the current directory. Make sure we can import it.
sys.path.append('.')

try:
    from _readdir2 import ffi, lib
except ImportError:
    print 'run readdir2_build first, then make sure the shared object is on sys.path'
    sys.exit(-1)

def walk(basefd, path):
    print '{', path
    dirfd = lib.openat(basefd, path, 0)
    if dirfd < 0:
        # error in openat()
        return
    dir = lib.fdopendir(dirfd)
    dirent = ffi.new("struct dirent *")
    result = ffi.new("struct dirent **")
    while True:
        if lib.readdir_r(dir, dirent, result):
            # error in readdir_r()
            break
        if result[0] == ffi.NULL:
            break
        name = ffi.string(dirent.d_name)
        print '%3d %s' % (dirent.d_type, name)
        if dirent.d_type == lib.DT_DIR and name != '.' and name != '..':
            walk(dirfd, name)
    lib.closedir(dir)
    print '}'


walk(-1, "/tmp")
