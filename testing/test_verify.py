import py
import sys, math
from cffi import FFI, VerificationError, VerificationMissing, model


if sys.platform != 'win32':
    class FFI(FFI):
        def verify(self, *args, **kwds):
            # XXX a GCC-only way to say "crash upon warnings too"
            return super(FFI, self).verify(
                *args, extra_compile_args=['-Werror'], **kwds)

def setup_module():
    import cffi.verifier
    cffi.verifier.cleanup_tmpdir()


def test_module_type():
    import cffi.verifier
    ffi = FFI()
    lib = ffi.verify()
    if hasattr(lib, '_cffi_python_module'):
        print('verify got a PYTHON module')
    if hasattr(lib, '_cffi_generic_module'):
        print('verify got a GENERIC module')
    expected_generic = (cffi.verifier._FORCE_GENERIC_ENGINE or
                        '__pypy__' in sys.builtin_module_names)
    assert hasattr(lib, '_cffi_python_module') == (not expected_generic)
    assert hasattr(lib, '_cffi_generic_module') == expected_generic

def test_missing_function(ffi=None):
    # uses the FFI hacked above with '-Werror'
    if ffi is None:
        ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    try:
        lib = ffi.verify()
    except (VerificationError, OSError):
        pass     # expected case: we get a VerificationError
    else:
        # but depending on compiler and loader details, maybe
        # 'lib' could actually be imported but will fail if we
        # actually try to call the unknown function...  Hard
        # to test anything more.
        pass

def test_missing_function_import_error():
    # uses the original FFI that just gives a warning during compilation
    import cffi
    test_missing_function(ffi=cffi.FFI())

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
    assert lib.strlen(b"hi there!") == 9

def test_strlen_approximate():
    ffi = FFI()
    ffi.cdef("int strlen(char *s);")
    lib = ffi.verify("#include <string.h>")
    assert lib.strlen(b"hi there!") == 9

def test_strlen_array_of_char():
    ffi = FFI()
    ffi.cdef("int strlen(char[]);")
    lib = ffi.verify("#include <string.h>")
    assert lib.strlen(b"hello") == 5

def test_longdouble():
    ffi = FFI()
    ffi.cdef("long double sinl(long double x);")
    lib = ffi.verify('#include <math.h>')
    for input in [1.23,
                  ffi.cast("double", 1.23),
                  ffi.cast("long double", 1.23)]:
        x = lib.sinl(input)
        assert repr(x).startswith("<cdata 'long double'")
        assert (float(x) - math.sin(1.23)) < 1E-10

def test_longdouble_precision():
    # Test that we don't loose any precision of 'long double' when
    # passing through Python and CFFI.
    ffi = FFI()
    ffi.cdef("long double step1(long double x);")
    lib = ffi.verify("""
        long double step1(long double x)
        {
            return 4*x-x*x;
        }
    """)
    def do(cast_to_double):
        x = 0.9789
        for i in range(10000):
            x = lib.step1(x)
            if cast_to_double:
                x = float(x)
        return float(x)

    more_precise = do(False)
    less_precise = do(True)
    assert abs(more_precise - less_precise) > 0.1

    # Check the particular results on Intel
    import platform
    if (platform.machine().startswith('i386') or
        platform.machine().startswith('x86')):
        assert abs(more_precise - 0.656769) < 0.001
        assert abs(less_precise - 3.99091) < 0.001
    else:
        py.test.skip("don't know the very exact precision of 'long double'")


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
    for typename in all_integer_types + all_float_types + ['char', 'wchar_t']:
        tp = model.PrimitiveType(typename)
        assert tp.is_char_type() == (typename in ('char', 'wchar_t'))
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
        if sys.version < '3':
            assert lib.foo(long(44)) == 45
        assert lib.foo(ffi.cast(typename, 46)) == 47
        py.test.raises(TypeError, lib.foo, ffi.NULL)
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

def test_nonstandard_integer_types():
    ffi = FFI()
    lst = ffi._backend.nonstandard_integer_types().items()
    lst = sorted(lst)
    verify_lines = []
    for key, value in lst:
        ffi.cdef("static const int expected_%s;" % key)
        verify_lines.append("static const int expected_%s =" % key)
        verify_lines.append("    sizeof(%s) | (((%s)-1) <= 0 ? 0 : 0x1000);"
                            % (key, key))
    lib = ffi.verify('\n'.join(verify_lines))
    for key, value in lst:
        assert getattr(lib, 'expected_%s' % key) == value

def test_char_type():
    ffi = FFI()
    ffi.cdef("char foo(char);")
    lib = ffi.verify("char foo(char x) { return x+1; }")
    assert lib.foo(b"A") == b"B"
    py.test.raises(TypeError, lib.foo, b"bar")
    py.test.raises(TypeError, lib.foo, "bar")

def test_wchar_type():
    ffi = FFI()
    if ffi.sizeof('wchar_t') == 2:
        uniexample1 = u'\u1234'
        uniexample2 = u'\u1235'
    else:
        uniexample1 = u'\U00012345'
        uniexample2 = u'\U00012346'
    #
    ffi.cdef("wchar_t foo(wchar_t);")
    lib = ffi.verify("wchar_t foo(wchar_t x) { return x+1; }")
    assert lib.foo(uniexample1) == uniexample2

def test_no_argument():
    ffi = FFI()
    ffi.cdef("int foo(void);")
    lib = ffi.verify("int foo(void) { return 42; }")
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
    assert lib.foo(ffi.NULL) == ffi.NULL
    p = ffi.new("int *", 42)
    q = ffi.new("int *", 42)
    assert lib.foo(p) == p
    assert lib.foo(q) != p

def test_bogus_ptr():
    ffi = FFI()
    ffi.cdef("int *foo(int *);")
    lib = ffi.verify("int *foo(int *a) { return a; }")
    py.test.raises(TypeError, lib.foo, ffi.new("short *", 42))


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
    assert lib.bar(ffi.NULL) == 42

def test_ffi_full_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { char x; int y; long *z; };")
    ffi.verify("struct foo_s { char x; int y; long *z; };")
    #
    if sys.platform == 'win32':
        py.test.skip("XXX fixme: only gives warnings")
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
    py.test.raises(VerificationMissing, ffi.new, 'struct foo_s *')
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
    if sys.platform == 'win32':
        py.test.skip("XXX fixme: only gives warnings")
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
    s = ffi.new("struct foo_s *")
    assert ffi.sizeof(s.a) == 17 * ffi.sizeof('int')

def test_struct_array_guess_length():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[]; ...; };")    # <= no declared length
    ffi.verify("struct foo_s { int x; int a[17]; int y; };")
    assert ffi.sizeof('struct foo_s') == 19 * ffi.sizeof('int')
    s = ffi.new("struct foo_s *")
    assert ffi.sizeof(s.a) == 17 * ffi.sizeof('int')

def test_struct_array_guess_length_2():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[]; ...; };\n"    # <= no declared length
             "int bar(struct foo_s *);\n")
    lib = ffi.verify("struct foo_s { int x; int a[17]; int y; };\n"
                     "int bar(struct foo_s *f) { return f->a[14]; }\n")
    assert ffi.sizeof('struct foo_s') == 19 * ffi.sizeof('int')
    s = ffi.new("struct foo_s *")
    s.a[14] = 4242
    assert lib.bar(s) == 4242

def test_struct_array_guess_length_3():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a[...]; };")
    ffi.verify("struct foo_s { int x; int a[17]; int y; };")
    assert ffi.sizeof('struct foo_s') == 19 * ffi.sizeof('int')
    s = ffi.new("struct foo_s *")
    assert ffi.sizeof(s.a) == 17 * ffi.sizeof('int')

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

def test_global_constants_non_int():
    ffi = FFI()
    ffi.cdef("static char *const PP;")
    lib = ffi.verify('static char *const PP = "testing!";\n')
    assert ffi.typeof(lib.PP) == ffi.typeof("char *")
    assert ffi.string(lib.PP) == b"testing!"

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
    lib = ffi.verify("enum ee { EE1, EE2, EE3, EE4 };")
    assert lib.EE3 == 2

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

def test_define_int():
    ffi = FFI()
    ffi.cdef("#define FOO ...\n"
             "\t#\tdefine\tBAR\t...\t")
    lib = ffi.verify("#define FOO 42\n"
                     "#define BAR (-44)\n")
    assert lib.FOO == 42
    assert lib.BAR == -44

def test_access_variable():
    ffi = FFI()
    ffi.cdef("int foo(void);\n"
             "int somenumber;")
    lib = ffi.verify("""
        static int somenumber = 2;
        static int foo(void) {
            return somenumber * 7;
        }
    """)
    assert lib.somenumber == 2
    assert lib.foo() == 14
    lib.somenumber = -6
    assert lib.foo() == -42
    assert lib.somenumber == -6
    lib.somenumber = 2   # reset for the next run, if any

def test_access_address_of_variable():
    # access the address of 'somenumber': need a trick
    ffi = FFI()
    ffi.cdef("int somenumber; static int *const somenumberptr;")
    lib = ffi.verify("""
        static int somenumber = 2;
        #define somenumberptr (&somenumber)
    """)
    assert lib.somenumber == 2
    lib.somenumberptr[0] = 42
    assert lib.somenumber == 42
    lib.somenumber = 2    # reset for the next run, if any

def test_access_array_variable(length=5):
    ffi = FFI()
    ffi.cdef("int foo(int);\n"
             "int somenumber[%s];" % (length,))
    lib = ffi.verify("""
        static int somenumber[] = {2, 2, 3, 4, 5};
        static int foo(int i) {
            return somenumber[i] * 7;
        }
    """)
    if length == '':
        # a global variable of an unknown array length is implicitly
        # transformed into a global pointer variable, because we can only
        # work with array instances whose length we know.  using a pointer
        # instead of an array gives the correct effects.
        assert repr(lib.somenumber).startswith("<cdata 'int *' 0x")
        py.test.raises(TypeError, len, lib.somenumber)
    else:
        assert repr(lib.somenumber).startswith("<cdata 'int[%s]' 0x" % length)
        assert len(lib.somenumber) == 5
    assert lib.somenumber[3] == 4
    assert lib.foo(3) == 28
    lib.somenumber[3] = -6
    assert lib.foo(3) == -42
    assert lib.somenumber[3] == -6
    assert lib.somenumber[4] == 5
    lib.somenumber[3] = 4    # reset for the next run, if any

def test_access_array_variable_length_hidden():
    test_access_array_variable(length='')

def test_access_struct_variable():
    ffi = FFI()
    ffi.cdef("struct foo { int x; ...; };\n"
             "int foo(int);\n"
             "struct foo stuff;")
    lib = ffi.verify("""
        struct foo { int x, y, z; };
        static struct foo stuff = {2, 5, 8};
        static int foo(int i) {
            switch (i) {
            case 0: return stuff.x * 7;
            case 1: return stuff.y * 7;
            case 2: return stuff.z * 7;
            }
            return -1;
        }
    """)
    assert lib.stuff.x == 2
    assert lib.foo(0) == 14
    assert lib.foo(1) == 35
    assert lib.foo(2) == 56
    lib.stuff.x = -6
    assert lib.foo(0) == -42
    assert lib.foo(1) == 35
    lib.stuff.x = 2      # reset for the next run, if any

def test_access_callback():
    ffi = FFI()
    ffi.cdef("int (*cb)(int);\n"
             "int foo(int);\n"
             "void reset_cb(void);")
    lib = ffi.verify("""
        static int g(int x) { return x * 7; }
        static int (*cb)(int);
        static int foo(int i) { return cb(i) - 1; }
        static void reset_cb(void) { cb = g; }
    """)
    lib.reset_cb()
    assert lib.foo(6) == 41
    my_callback = ffi.callback("int(*)(int)", lambda n: n * 222)
    lib.cb = my_callback
    assert lib.foo(4) == 887

def test_access_callback_function_typedef():
    ffi = FFI()
    ffi.cdef("typedef int mycallback_t(int);\n"
             "mycallback_t *cb;\n"
             "int foo(int);\n"
             "void reset_cb(void);")
    lib = ffi.verify("""
        static int g(int x) { return x * 7; }
        static int (*cb)(int);
        static int foo(int i) { return cb(i) - 1; }
        static void reset_cb(void) { cb = g; }
    """)
    lib.reset_cb()
    assert lib.foo(6) == 41
    my_callback = ffi.callback("int(*)(int)", lambda n: n * 222)
    lib.cb = my_callback
    assert lib.foo(4) == 887

def test_ctypes_backend_forces_generic_engine():
    from cffi.backend_ctypes import CTypesBackend
    ffi = FFI(backend=CTypesBackend())
    ffi.cdef("int func(int a);")
    lib = ffi.verify("int func(int a) { return a * 42; }")
    assert not hasattr(lib, '_cffi_python_module')
    assert hasattr(lib, '_cffi_generic_module')
    assert lib.func(100) == 4200

def test_call_with_struct_ptr():
    ffi = FFI()
    ffi.cdef("typedef struct { int x; ...; } foo_t; int foo(foo_t *);")
    lib = ffi.verify("""
        typedef struct { int y, x; } foo_t;
        static int foo(foo_t *f) { return f->x * 7; }
    """)
    f = ffi.new("foo_t *")
    f.x = 6
    assert lib.foo(f) == 42

def test_unknown_type():
    ffi = FFI()
    ffi.cdef("""
        typedef ... token_t;
        int foo(token_t *);
        #define TOKEN_SIZE ...
    """)
    lib = ffi.verify("""
        typedef float token_t;
        static int foo(token_t *tk) {
            if (!tk)
                return -42;
            *tk += 1.601;
            return (int)*tk;
        }
        #define TOKEN_SIZE sizeof(token_t)
    """)
    # we cannot let ffi.new("token_t *") work, because we don't know ahead of
    # time if it's ok to ask 'sizeof(token_t)' in the C code or not.
    # See test_unknown_type_2.  Workaround.
    tkmem = ffi.new("char[]", lib.TOKEN_SIZE)    # zero-initialized
    tk = ffi.cast("token_t *", tkmem)
    results = [lib.foo(tk) for i in range(6)]
    assert results == [1, 3, 4, 6, 8, 9]
    assert lib.foo(ffi.NULL) == -42

def test_unknown_type_2():
    ffi = FFI()
    ffi.cdef("typedef ... token_t;")
    lib = ffi.verify("typedef struct token_s token_t;")
    # assert did not crash, even though 'sizeof(token_t)' is not valid in C.

def test_varargs():
    ffi = FFI()
    ffi.cdef("int foo(int x, ...);")
    lib = ffi.verify("""
        int foo(int x, ...) {
            va_list vargs;
            va_start(vargs, x);
            x -= va_arg(vargs, int);
            x -= va_arg(vargs, int);
            va_end(vargs);
            return x;
        }
    """)
    assert lib.foo(50, ffi.cast("int", 5), ffi.cast("int", 3)) == 42

def test_varargs_exact():
    if sys.platform == 'win32':
        py.test.skip("XXX fixme: only gives warnings")
    ffi = FFI()
    ffi.cdef("int foo(int x, ...);")
    py.test.raises(VerificationError, ffi.verify, """
        int foo(long long x, ...) {
            return x;
        }
    """)

def test_varargs_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { char a; int b; }; int foo(int x, ...);")
    lib = ffi.verify("""
        struct foo_s {
            char a; int b;
        };
        int foo(int x, ...) {
            va_list vargs;
            struct foo_s s;
            va_start(vargs, x);
            s = va_arg(vargs, struct foo_s);
            va_end(vargs);
            return s.a - s.b;
        }
    """)
    s = ffi.new("struct foo_s *", [b'B', 1])
    assert lib.foo(50, s[0]) == ord('A')

def test_autofilled_struct_as_argument():
    ffi = FFI()
    ffi.cdef("struct foo_s { long a; double b; ...; };\n"
             "int foo(struct foo_s);")
    lib = ffi.verify("""
        struct foo_s {
            double b;
            long a;
        };
        int foo(struct foo_s s) {
            return s.a - (int)s.b;
        }
    """)
    s = ffi.new("struct foo_s *", [100, 1])
    assert lib.foo(s[0]) == 99
    assert lib.foo([100, 1]) == 99

def test_autofilled_struct_as_argument_dynamic():
    ffi = FFI()
    ffi.cdef("struct foo_s { long a; ...; };\n"
             "int (*foo)(struct foo_s);")
    e = py.test.raises(TypeError, ffi.verify, """
        struct foo_s {
            double b;
            long a;
        };
        int foo1(struct foo_s s) {
            return s.a - (int)s.b;
        }
        int (*foo)(struct foo_s s) = &foo1;
    """)
    msg ='cannot pass as an argument a struct that was completed with verify()'
    assert msg in str(e.value)

def test_func_returns_struct():
    ffi = FFI()
    ffi.cdef("""
        struct foo_s { int aa, bb; };
        struct foo_s foo(int a, int b);
    """)
    lib = ffi.verify("""
        struct foo_s { int aa, bb; };
        struct foo_s foo(int a, int b) {
            struct foo_s r;
            r.aa = a*a;
            r.bb = b*b;
            return r;
        }
    """)
    s = lib.foo(6, 7)
    assert repr(s) == "<cdata 'struct foo_s' owning 8 bytes>"
    assert s.aa == 36
    assert s.bb == 49

def test_func_as_funcptr():
    ffi = FFI()
    ffi.cdef("int *(*const fooptr)(void);")
    lib = ffi.verify("""
        int *foo(void) {
            return (int*)"foobar";
        }
        int *(*fooptr)(void) = foo;
    """)
    foochar = ffi.cast("char *(*)(void)", lib.fooptr)
    s = foochar()
    assert ffi.string(s) == b"foobar"

def test_funcptr_as_argument():
    ffi = FFI()
    ffi.cdef("""
        void qsort(void *base, size_t nel, size_t width,
            int (*compar)(const void *, const void *));
    """)
    ffi.verify("#include <stdlib.h>")

def test_func_as_argument():
    ffi = FFI()
    ffi.cdef("""
        void qsort(void *base, size_t nel, size_t width,
            int compar(const void *, const void *));
    """)
    ffi.verify("#include <stdlib.h>")

def test_array_as_argument():
    ffi = FFI()
    ffi.cdef("""
        int strlen(char string[]);
    """)
    ffi.verify("#include <string.h>")

def test_enum_as_argument():
    ffi = FFI()
    ffi.cdef("""
        enum foo_e { AA, BB, ... };
        int foo_func(enum foo_e);
    """)
    lib = ffi.verify("""
        enum foo_e { AA, CC, BB };
        int foo_func(enum foo_e e) { return e; }
    """)
    assert lib.foo_func(lib.BB) == 2
    assert lib.foo_func("BB") == 2

def test_enum_as_function_result():
    ffi = FFI()
    ffi.cdef("""
        enum foo_e { AA, BB, ... };
        enum foo_e foo_func(int x);
    """)
    lib = ffi.verify("""
        enum foo_e { AA, CC, BB };
        enum foo_e foo_func(int x) { return x; }
    """)
    assert lib.foo_func(lib.BB) == "BB"

def test_callback_calling_convention():
    py.test.skip("later")
    if sys.platform != 'win32':
        py.test.skip("Windows only")
    ffi = FFI()
    ffi.cdef("""
        int call1(int(*__cdecl cb)(int));
        int call2(int(*__stdcall cb)(int));
    """)
    lib = ffi.verify("""
        int call1(int(*__cdecl cb)(int)) {
            return cb(42) + 1;
        }
        int call2(int(*__stdcall cb)(int)) {
            return cb(-42) - 6;
        }
    """)
    xxx

def test_opaque_integer_as_function_result():
    # XXX bad abuse of "struct { ...; }".  It only works a bit by chance
    # anyway.  XXX think about something better :-(
    ffi = FFI()
    ffi.cdef("""
        typedef struct { ...; } myhandle_t;
        myhandle_t foo(void);
    """)
    lib = ffi.verify("""
        typedef short myhandle_t;
        myhandle_t foo(void) { return 42; }
    """)
    h = lib.foo()
    assert ffi.sizeof(h) == ffi.sizeof("short")
