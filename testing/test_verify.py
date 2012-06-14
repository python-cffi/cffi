import py
import math
from cffi import FFI, VerificationError, VerificationMissing, model


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
all_signed_integer_types = [_typename for _typename in all_integer_types
                                      if not _typename.startswith('unsigned ')]
all_unsigned_integer_types = [_typename for _typename in all_integer_types
                                        if _typename.startswith('unsigned ')]
all_float_types = ['float', 'double']

def test_primitive_category():
    for typename in all_integer_types + all_float_types + ['char']:
        tp = model.PrimitiveType(typename)
        assert tp.is_char_type() == (typename == 'char')
        assert tp.is_signed_type() == (typename in all_signed_integer_types)
        assert tp.is_unsigned_type()== (typename in all_unsigned_integer_types)
        assert tp.is_integer_type() == (typename in all_integer_types)
        assert tp.is_float_type() == (typename in all_float_types)

def test_all_integer_and_float_types():
    for typename in all_integer_types + all_float_types:
        ffi = FFI()
        ffi.cdef("%s foo(%s);" % (typename, typename))
        lib = ffi.verify("%s foo(%s x) { return x+1; }" % (typename, typename))
        assert lib.foo(42) == 43
        assert lib.foo(44L) == 45
        assert lib.foo(ffi.cast(typename, 46)) == 47
        py.test.raises(TypeError, lib.foo, None)
        #
        # check for overflow cases
        if typename in all_float_types:
            continue
        for value in [-2**80, -2**40, -2**20, -2**10, -2**5, -1,
                      2**5, 2**10, 2**20, 2**40, 2**80]:
            overflows = int(ffi.cast(typename, value)) != value
            if overflows:
                py.test.raises(OverflowError, lib.foo, value)
            else:
                assert lib.foo(value) == value + 1

def test_char_type():
    ffi = FFI()
    ffi.cdef("char foo(char);")
    lib = ffi.verify("char foo(char x) { return x+1; }")
    assert lib.foo("A") == "B"
    py.test.raises(TypeError, lib.foo, "bar")

def test_no_argument():
    ffi = FFI()
    ffi.cdef("int foo(void);")
    lib = ffi.verify("int foo() { return 42; }")
    assert lib.foo() == 42

def test_two_arguments():
    ffi = FFI()
    ffi.cdef("int foo(int, int);")
    lib = ffi.verify("int foo(int a, int b) { return a - b; }")
    assert lib.foo(40, -2) == 42

def test_macro():
    ffi = FFI()
    ffi.cdef("int foo(int, int);")
    lib = ffi.verify("#define foo(a, b) ((a) * (b))")
    assert lib.foo(-6, -7) == 42

def test_ptr():
    ffi = FFI()
    ffi.cdef("int *foo(int *);")
    lib = ffi.verify("int *foo(int *a) { return a; }")
    assert lib.foo(None) is None
    p = ffi.new("int", 42)
    q = ffi.new("int", 42)
    assert lib.foo(p) == p
    assert lib.foo(q) != p

def test_bogus_ptr():
    ffi = FFI()
    ffi.cdef("int *foo(int *);")
    lib = ffi.verify("int *foo(int *a) { return a; }")
    py.test.raises(TypeError, lib.foo, ffi.new("short", 42))


def test_verify_typedefs():
    py.test.skip("ignored so far")
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

def test_nondecl_struct():
    ffi = FFI()
    ffi.cdef("typedef struct foo_s foo_t; int bar(foo_t *);")
    lib = ffi.verify("typedef struct foo_s foo_t;\n"
                     "int bar(foo_t *f) { return 42; }\n")
    assert lib.bar(None) == 42

def test_missing_typedef():
    ffi = FFI()
    ffi.cdef("typedef...foo_t; int bar(foo_t *);")
    py.test.raises(TypeError, ffi.new, "foo_t")
    lib = ffi.verify("typedef struct foo_s { int x; } foo_t;\n"
                     "int bar(foo_t *f) { return 42; }\n")
    py.test.raises(TypeError, ffi.new, "foo_t")
    f = ffi.cast("foo_t*", 0)
    assert lib.bar(f) == 42


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
    assert ffi.sizeof('struct foo_s') == 6 * ffi.sizeof('int')
    assert ffi.offsetof('struct foo_s', 'x') == 2 * ffi.sizeof('int')

def test_ffi_nonfull_alignment():
    ffi = FFI()
    ffi.cdef("struct foo_s { char x; ...; };")
    ffi.verify("struct foo_s { int a, b; char x; };")
    assert ffi.sizeof('struct foo_s') == 3 * ffi.sizeof('int')
    assert ffi.alignof('struct foo_s') == ffi.sizeof('int')

def _check_field_match(typename, real, expect_mismatch):
    ffi = FFI()
    if expect_mismatch == 'by_size':
        expect_mismatch = ffi.sizeof(typename) != ffi.sizeof(real)
    ffi.cdef("struct foo_s { %s x; ...; };" % typename)
    try:
        ffi.verify("struct foo_s { %s x; };" % real)
    except VerificationError:
        if not expect_mismatch:
            raise AssertionError("unexpected mismatch: %s should be accepted "
                                 "as equal to %s" % (typename, real))
    else:
        if expect_mismatch:
            raise AssertionError("mismatch not detected: "
                                 "%s != %s" % (typename, real))

def test_struct_bad_sized_integer():
    for typename in all_signed_integer_types:
        for real in all_signed_integer_types:
            _check_field_match(typename, real, "by_size")

def test_struct_bad_sized_float():
    for typename in all_float_types:
        for real in all_float_types:
            _check_field_match(typename, real, "by_size")

def test_struct_signedness_ignored():
    _check_field_match("int", "unsigned int", expect_mismatch=False)
    _check_field_match("unsigned short", "signed short", expect_mismatch=False)

def test_struct_float_vs_int():
    for typename in all_signed_integer_types:
        for real in all_float_types:
            _check_field_match(typename, real, expect_mismatch=True)
    for typename in all_float_types:
        for real in all_signed_integer_types:
            _check_field_match(typename, real, expect_mismatch=True)

def test_struct_array_field():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[17]; ...; };")
    ffi.verify("struct foo_s { int x; int a[17]; int y; };")
    assert ffi.sizeof('struct foo_s') == 19 * ffi.sizeof('int')
    s = ffi.new("struct foo_s")
    assert ffi.sizeof(s.a) == 17 * ffi.sizeof('int')

def test_struct_array_guess_length():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[]; ...; };")    # <= no declared length
    ffi.verify("struct foo_s { int x; int a[17]; int y; };")
    assert ffi.sizeof('struct foo_s') == 19 * ffi.sizeof('int')
    s = ffi.new("struct foo_s")
    assert ffi.sizeof(s.a) == 17 * ffi.sizeof('int')

def test_struct_array_guess_length_2():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[]; ...; };\n"    # <= no declared length
             "int bar(struct foo_s *);\n")
    lib = ffi.verify("struct foo_s { int x; int a[17]; int y; };\n"
                     "int bar(struct foo_s *f) { return f->a[14]; }\n")
    assert ffi.sizeof('struct foo_s') == 19 * ffi.sizeof('int')
    s = ffi.new("struct foo_s")
    s.a[14] = 4242
    assert lib.bar(s) == 4242

def test_global_constants():
    ffi = FFI()
    # use 'static const int', as generally documented, although in this
    # case the 'static' is completely ignored.
    ffi.cdef("static const int AA, BB, CC, DD;")
    lib = ffi.verify("#define AA 42\n"
                     "#define BB (-43)\n"
                     "#define CC (22*2)\n"
                     "#define DD ((unsigned int)142)\n")
    assert lib.AA == 42
    assert lib.BB == -43
    assert lib.CC == 44
    assert lib.DD == 142

def test_global_const_int_size():
    # integer constants: ignore the declared type, always just use the value
    for value in [-2**63, -2**31, -2**15,
                  2**15-1, 2**15, 2**31-1, 2**31, 2**32-1, 2**32,
                  2**63-1, 2**63, 2**64-1]:
        ffi = FFI()
        if value == int(ffi.cast("long long", value)):
            if value < 0:
                vstr = '(-%dLL-1)' % (~value,)
            else:
                vstr = '%dLL' % value
        elif value == int(ffi.cast("unsigned long long", value)):
            vstr = '%dULL' % value
        else:
            raise AssertionError(value)
        ffi.cdef("static const unsigned short AA;")
        lib = ffi.verify("#define AA %s\n" % vstr)
        assert lib.AA == value
        assert type(lib.AA) is type(int(lib.AA))

def test_nonfull_enum():
    ffi = FFI()
    ffi.cdef("enum ee { EE1, EE2, EE3, ... \n \t };")
    py.test.raises(VerificationMissing, ffi.cast, 'enum ee', 'EE2')
    ffi.verify("enum ee { EE1=10, EE2, EE3=-10, EE4 };")
    assert int(ffi.cast('enum ee', 'EE2')) == 11
    assert int(ffi.cast('enum ee', 'EE3')) == -10
    py.test.raises(ValueError, ffi.cast, 'enum ee', '__dotdotdot0__')

def test_full_enum():
    ffi = FFI()
    ffi.cdef("enum ee { EE1, EE2, EE3 };")
    ffi.verify("enum ee { EE1, EE2, EE3 };")
    py.test.raises(VerificationError, ffi.verify, "enum ee { EE1, EE2 };")
    e = py.test.raises(VerificationError, ffi.verify,
                       "enum ee { EE1, EE3, EE2 };")
    assert str(e.value) == 'in enum ee: EE2 has the real value 2, not 1'
    # extra items cannot be seen and have no bad consequence anyway
    ffi.verify("enum ee { EE1, EE2, EE3, EE4 };")

def test_get_set_errno():
    ffi = FFI()
    ffi.cdef("int foo(int);")
    lib = ffi.verify("""
        static int foo(int x)
        {
            errno += 1;
            return x * 7;
        }
    """)
    ffi.errno = 15
    assert lib.foo(6) == 42
    assert ffi.errno == 16
