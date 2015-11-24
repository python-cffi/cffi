import sys, os

# If the build script was run immediately before this script, the cffi module
# ends up in the current directory. Make sure we can import it.
sys.path.append('.')

try:
    from _xclient import ffi, lib
except ImportError:
    print 'run xclient_build first, then make sure the shared object is on sys.path'
    sys.exit(-1)

# ffi "knows" about the declared variables and functions from the
#     cdef parts of the module xclient_build created,
# lib "knows" how to call the functions from the set_source parts
#     of the module.


class XError(Exception):
    pass

def main():
    display = lib.XOpenDisplay(ffi.NULL)
    if display == ffi.NULL:
        raise XError("cannot open display")
    w = lib.XCreateSimpleWindow(display, lib.DefaultRootWindow(display),
                            10, 10, 500, 350, 0, 0, 0)
    lib.XMapRaised(display, w)
    event = ffi.new("XEvent *")
    lib.XNextEvent(display, event)

if __name__ == '__main__':
    main()
