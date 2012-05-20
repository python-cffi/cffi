import py
from ffi import FFI
import math, os, cStringIO


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


def test_sin():
    ffi = FFI()
    ffi.cdef("""
        double sin(double x);
    """)
    m = ffi.load("m")
    x = m.sin(1.23)
    assert x == math.sin(1.23)

def test_sinf():
    ffi = FFI()
    ffi.cdef("""
        float sinf(float x);
    """)
    m = ffi.load("m")
    x = m.sinf(1.23)
    assert type(x) is float
    assert x != math.sin(1.23)    # rounding effects
    assert abs(x - math.sin(1.23)) < 1E-6

def test_puts():
    ffi = FFI()
    ffi.cdef("""
       int puts(const char *);
       int fflush(void *);
    """)
    with FdWriteCapture() as fd:
        ffi.C.puts("hello")
        ffi.C.puts("  world")
        ffi.C.fflush(None)
    res = fd.getvalue()
    assert res == 'hello\n  world\n'

def test_vararg():
    ffi = FFI()
    ffi.cdef("""
       int printf(const char *format, ...);
       int fflush(void *);
    """)
    with FdWriteCapture() as fd:
        ffi.C.printf("hello\n")
        ffi.C.printf("hello, %s!\n", ffi.new("const char *", "world"))
        ffi.C.printf("hello int %d long %ld long long %lld\n",
                     ffi.new("int", 42),
                     ffi.new("long", 84),
                     ffi.new("long long", 168))
        ffi.C.fflush(None)
    res = fd.getvalue()
    assert res == ("hello\n"
                   "hello, world!\n"
                   "hello int 42 long 84 long long 168\n")

def test_must_specify_type_of_vararg():
    ffi = FFI()
    ffi.cdef("""
       int printf(const char *format, ...);
    """)
    e = py.test.raises(TypeError, ffi.C.printf, "hello %d\n", 42)
    assert str(e.value) == 'argument 2 needs to be a cdata'

def test_function_pointer():
    py.test.skip("in-progress")
    ffi = FFI()
    ffi.cdef("""
        int puts(const char *);
        int fflush(void *);
    """)
    f = ffi.new("int(*)(const char *txt)", ffi.C.puts)
    assert f == ffi.new("int(*)(const char *)", ffi.C.puts)
    with FdWriteCapture() as fd:
        f("hello")
        ffi.C.fflush(None)
    res = fd.getvalue()
    assert res == 'hello\n'

def test_passing_array():
    ffi = FFI()
    ffi.cdef("""
        int strlen(char[]);
    """)
    p = ffi.new("char[]", "hello")
    res = ffi.C.strlen(p)
    assert res == 5
