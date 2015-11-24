import sys, os

# If the build script was run immediately before this script, the cffi module
# ends up in the current directory. Make sure we can import it.
sys.path.append('.')

try:
    from _pwuid import ffi, lib
except ImportError:
    print 'run pwuid_build first, then make sure the shared object is on sys.path'
    sys.exit(-1)

# ffi "knows" about the declared variables and functions from the
#     cdef parts of the module xclient_build created,
# lib "knows" how to call the functions from the set_source parts
#     of the module.

print ffi.string(lib.getpwuid(0).pw_name)
