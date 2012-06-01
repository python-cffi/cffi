import py
from ffi import FFI
import math, os
from ffi.backend_ctypes import CTypesBackend


class FdWriteCapture(object):
    """xxx limited to capture at most 512 bytes of output, according
    to the Posix manual."""

    def __init__(self, capture_fd=1):   # stdout, by default
        self.capture_fd = capture_fd

    def __enter__(self):
        self.read_fd, self.write_fd = os.pipe()
        self.copy_fd = os.dup(self.capture_fd)
        os.dup2(self.write_fd, self.capture_fd)
        return self

    def __exit__(self, *args):
        os.dup2(self.copy_fd, self.capture_fd)
        os.close(self.copy_fd)
        os.close(self.write_fd)
        self._value = os.read(self.read_fd, 512)
        os.close(self.read_fd)

    def getvalue(self):
        return self._value


class TestFunction(object):
    Backend = CTypesBackend

    def test_sin(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            double sin(double x);
        """)
        m = ffi.load("m")
        x = m.sin(1.23)
        assert x == math.sin(1.23)

    def test_sinf(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            float sinf(float x);
        """)
        m = ffi.load("m")
        x = m.sinf(1.23)
        assert type(x) is float
        assert x != math.sin(1.23)    # rounding effects
        assert abs(x - math.sin(1.23)) < 1E-6

    def test_puts(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int puts(const char *);
            int fflush(void *);
        """)
        ffi.C.puts   # fetch before capturing, for easier debugging
        with FdWriteCapture() as fd:
            ffi.C.puts("hello")
            ffi.C.puts("  world")
            ffi.C.fflush(None)
        res = fd.getvalue()
        assert res == 'hello\n  world\n'

    def test_puts_wihtout_const(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int puts(char *);
            int fflush(void *);
        """)
        ffi.C.puts   # fetch before capturing, for easier debugging
        with FdWriteCapture() as fd:
            ffi.C.puts("hello")
            ffi.C.puts("  world")
            ffi.C.fflush(None)
        res = fd.getvalue()
        assert res == 'hello\n  world\n'

    def test_fputs(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int fputs(const char *, void *);
            void *stdout, *stderr;
        """)
        with FdWriteCapture(2) as fd:
            ffi.C.fputs("hello from stderr\n", ffi.C.stderr)
        res = fd.getvalue()
        assert res == 'hello from stderr\n'

    def test_vararg(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
           int printf(const char *format, ...);
           int fflush(void *);
        """)
        with FdWriteCapture() as fd:
            ffi.C.printf("hello with no arguments\n")
            ffi.C.printf("hello, %s!\n", ffi.new("char[]", "world"))
            ffi.C.printf(ffi.new("char[]", "hello, %s!\n"),
                         ffi.new("char[]", "world2"))
            ffi.C.printf("hello int %d long %ld long long %lld\n",
                         ffi.cast("int", 42),
                         ffi.cast("long", 84),
                         ffi.cast("long long", 168))
            ffi.C.printf("hello %p\n", None)
            ffi.C.fflush(None)
        res = fd.getvalue()
        assert res == ("hello with no arguments\n"
                       "hello, world!\n"
                       "hello, world2!\n"
                       "hello int 42 long 84 long long 168\n"
                       "hello (nil)\n")

    def test_must_specify_type_of_vararg(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
           int printf(const char *format, ...);
        """)
        e = py.test.raises(TypeError, ffi.C.printf, "hello %d\n", 42)
        assert str(e.value) == ("argument 2 passed in the variadic part "
                                "needs to be a cdata object (got int)")

    def test_function_has_a_c_type(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int puts(const char *);
        """)
        fptr = ffi.C.puts
        assert ffi.typeof(fptr) == ffi.typeof("int(*)(const char*)")
        if self.Backend is CTypesBackend:
            assert repr(fptr) == "<cdata 'int puts(char *)'>"

    def test_function_pointer(self):
        ffi = FFI(backend=self.Backend())
        def cb(charp):
            assert repr(charp) == "<cdata 'char *'>"
            return 42
        fptr = ffi.callback("int(*)(const char *txt)", cb)
        assert fptr != ffi.callback("int(*)(const char *)", cb)
        assert repr(fptr) == "<cdata 'int(*)(char *)' calling %r>" % (cb,)
        res = fptr("Hello")
        assert res == 42
        #
        ffi.cdef("""
            int puts(const char *);
            int fflush(void *);
        """)
        fptr = ffi.cast("int(*)(const char *txt)", ffi.C.puts)
        assert fptr == ffi.C.puts
        assert repr(fptr) == "<cdata 'int(*)(char *)'>"
        with FdWriteCapture() as fd:
            fptr("world")
            ffi.C.fflush(None)
        res = fd.getvalue()
        assert res == 'world\n'

    def test_passing_array(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int strlen(char[]);
        """)
        p = ffi.new("char[]", "hello")
        res = ffi.C.strlen(p)
        assert res == 5

    def test_write_variable(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int puts(const char *);
            void *stdout, *stderr;
        """)
        pout = ffi.C.stdout
        perr = ffi.C.stderr
        assert repr(pout) == "<cdata 'void *'>"
        assert repr(perr) == "<cdata 'void *'>"
        with FdWriteCapture(2) as fd:     # capturing stderr
            ffi.C.stdout = perr
            try:
                ffi.C.puts("hello!") # goes to stdout, which is equal to stderr now
            finally:
                ffi.C.stdout = pout
        res = fd.getvalue()
        assert res == "hello!\n"

    def test_strchr(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            char *strchr(const char *s, int c);
        """)
        p = ffi.new("char[]", "hello world!")
        q = ffi.C.strchr(p, ord('w'))
        assert str(q) == "world!"

    def test_function_with_struct_argument(self):
        py.test.skip("in-progress")

    def test_function_with_struct_return(self):
        py.test.skip("in-progress")
