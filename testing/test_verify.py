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


def test_verify_typedefs():
    types = ['signed char', 'unsigned char', 'int', 'long']
    for cdefed in types:
        for real in types:
            ffi = FFI()
            ffi.cdef("typedef %s foo_t;" % cdefed)
            if cdefed == real:
                ffi.verify("typedef %s foo_t;" % real)
            else:
                py.test.raises(VerificationError, ffi.verify,
                               "typedef %s foo_t;" % real)


def test_ffi_full_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { char x; int y; long *z; };")
    ffi.verify("struct foo_s { char x; int y; long *z; };")
    #
    for real in [
        "struct foo_s { char x; int y; int *z; };",
        "struct foo_s { char x; long *z; int y; };",
        "struct foo_s { int y; long *z; };",
        "struct foo_s { char x; int y; long *z; char extra; };",
        ]:
        py.test.raises(VerificationError, ffi.verify, real)
    #
    # a corner case that we cannot really detect, but where it has no
    # bad consequences: the size is the same, but there is an extra field
    # that replaces what is just padding in our declaration above
    ffi.verify("struct foo_s { char x, extra; int y; long *z; };")


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
