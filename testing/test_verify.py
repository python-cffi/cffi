import py
import math
from cffi import FFI, VerificationError, VerificationMissing


def test_missing_function():
    ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    py.test.raises(VerificationError, ffi.verify)

def test_simple_case():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    lib = ffi.verify('#include <math.h>')
    assert lib.sin(1.23) == math.sin(1.23)

def test_rounding_1():
    ffi = FFI()
    ffi.cdef("float sin(double x);")
    lib = ffi.verify('#include <math.h>')
    res = lib.sin(1.23)
    assert res != math.sin(1.23)     # not exact, because of double->float
    assert abs(res - math.sin(1.23)) < 1E-5

def test_rounding_2():
    ffi = FFI()
    ffi.cdef("double sin(float x);")
    lib = ffi.verify('#include <math.h>')
    res = lib.sin(1.23)
    assert res != math.sin(1.23)     # not exact, because of double->float
    assert abs(res - math.sin(1.23)) < 1E-5

def test_strlen_exact():
    ffi = FFI()
    ffi.cdef("size_t strlen(const char *s);")
    lib = ffi.verify("#include <string.h>")
    assert lib.strlen("hi there!") == 9

def test_strlen_approximate():
    ffi = FFI()
    ffi.cdef("int strlen(char *s);")
    lib = ffi.verify("#include <string.h>")
    assert lib.strlen("hi there!") == 9


all_integer_types = ['short', 'int', 'long', 'long long',
                     'signed char', 'unsigned char',
                     'unsigned short', 'unsigned int',
                     'unsigned long', 'unsigned long long']
all_float_types = ['float', 'double']

def test_all_integer_and_float_types():
    for typename in all_integer_types + all_float_types:
        ffi = FFI()
        ffi.cdef("%s foo(%s);" % (typename, typename))
        lib = ffi.verify("%s foo(%s x) { return x+1; }" % (typename, typename))
        assert lib.foo(42) == 43


def test_verify_typedefs():
    py.test.skip("XXX?")
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
    py.test.skip("XXX?")
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
