import py, sys
from testing import backend_tests, test_function, test_ownlib
from cffi import FFI
import _cffi_backend


class TestFFI(backend_tests.BackendTests,
              test_function.TestFunction,
              test_ownlib.TestOwnLib):
    TypeRepr = "<ctype '%s'>"

    @staticmethod
    def Backend():
        return _cffi_backend

    def test_not_supported_bitfield_in_result(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int a,b,c,d,e; int x:1; };")
        e = py.test.raises(NotImplementedError, ffi.callback,
                           "struct foo_s foo(void)", lambda: 42)
        assert str(e.value) == ("<struct foo_s(*)(void)>: "
            "cannot pass as argument or return value a struct with bit fields")

    def test_inspecttype(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.typeof("long").kind == "primitive"
        assert ffi.typeof("long(*)(long, long**, ...)").cname == (
            "long(*)(long, long * *, ...)")
        assert ffi.typeof("long(*)(long, long**, ...)").ellipsis is True

    def test_new_handle(self):
        ffi = FFI(backend=self.Backend())
        o = [2, 3, 4]
        p = ffi.new_handle(o)
        assert ffi.typeof(p) == ffi.typeof("void *")
        assert ffi.from_handle(p) is o
        assert ffi.from_handle(ffi.cast("char *", p)) is o
        py.test.raises(RuntimeError, ffi.from_handle, ffi.NULL)


class TestBitfield:
    def check(self, source, expected_ofs_y, expected_align, expected_size):
        # verify the information with gcc
        if sys.platform != "win32":
            ffi1 = FFI()
            ffi1.cdef("static const int Gofs_y, Galign, Gsize;")
            lib = ffi1.verify("""
                struct s1 { %s };
                struct sa { char a; struct s1 b; };
                #define Gofs_y  offsetof(struct s1, y)
                #define Galign  offsetof(struct sa, b)
                #define Gsize   sizeof(struct s1)
            """ % source)
            assert lib.Gofs_y == expected_ofs_y
            assert lib.Galign == expected_align
            assert lib.Gsize  == expected_size
        # the real test follows
        ffi = FFI()
        ffi.cdef("struct s1 { %s };" % source)
        assert ffi.offsetof("struct s1", "y") == expected_ofs_y
        assert ffi.alignof("struct s1") == expected_align
        assert ffi.sizeof("struct s1") == expected_size

    def test_bitfield_basic(self):
        self.check("int a; int b:9; int c:20; int y;", 8, 4, 12)
        self.check("int a; short b:9; short c:7; int y;", 8, 4, 12)
        self.check("int a; short b:9; short c:9; int y;", 8, 4, 12)

    def test_bitfield_reuse_if_enough_space(self):
        self.check("char a; int b:9; char y;", 3, 4, 4)
        self.check("char a; short b:9; char y;", 4, 2, 6)

    def test_bitfield_anonymous_no_align(self):
        L = FFI().alignof("long long")
        self.check("char x; int z:1; char y;", 2, 4, 4)
        self.check("char x; int  :1; char y;", 2, 1, 3)
        self.check("char x; long long z:48; char y;", 7, L, 8)
        self.check("char x; long long  :48; char y;", 7, 1, 8)
        self.check("char x; long long z:56; char y;", 8, L, 8 + L)
        self.check("char x; long long  :56; char y;", 8, 1, 9)
        self.check("char x; long long z:57; char y;", L + 8, L, L + 8 + L)
        self.check("char x; long long  :57; char y;", L + 8, 1, L + 9)

    def test_bitfield_zero(self):
        L = FFI().alignof("long long")
        self.check("char x; int :0; char y;", 4, 1, 5)
        self.check("char x; long long :0; char y;", L, 1, L + 1)
