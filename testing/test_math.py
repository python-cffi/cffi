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
       void puts(const char *);
       int fflush(void *);
    """)
    with FdWriteCapture() as fd:
        ffi.C.puts("hello")
        ffi.C.puts("  world")
        ffi.C.fflush(None)
    res = fd.getvalue()
    assert res == 'hello\n  world\n'
