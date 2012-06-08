import py
from cffi import FFI, VerificationError, VerificationMissing


def test_simple_verify():
    ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    py.test.raises(VerificationError, ffi.verify)
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    # omission of math.h
    py.test.raises(VerificationError, ffi.verify)
    assert ffi.verify('#include <math.h>') is None
    #
    ffi = FFI()
    ffi.cdef("float sin(double x);")
    py.test.raises(VerificationError, ffi.verify, '#include <math.h>')
    ffi = FFI()
    ffi.cdef("double sin(float x);")
    py.test.raises(VerificationError, ffi.verify, '#include <math.h>')
    #
    ffi = FFI()
    ffi.cdef("size_t strlen(const char *s);")
    ffi.verify("#include <string.h>")


def test_ffi_nonfull_struct():
    py.test.skip("XXX")
    ffi = FFI()
    ffi.cdef("""
    struct foo_s {
       int x;
       ...;
    };
    """)
    py.test.raises(VerificationMissing, ffi.sizeof, 'struct foo_s')
    py.test.raises(VerificationMissing, ffi.offsetof, 'struct foo_s', 'x')
    py.test.raises(VerificationMissing, ffi.new, 'struct foo_s')
    ffi.verify("""
    struct foo_s {
       int a, b, x, c, d, e;
    };
    """)
    assert ffi.sizeof('struct foo_s') == 6 * ffi.sizeof(int)
    assert ffi.offsetof('struct foo_s', 'x') == 2 * ffi.sizeof(int)
