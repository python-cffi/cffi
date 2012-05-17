from ffi import FFI
import math


def test_sin():
    ffi = FFI()
    ffi.cdef("""
        double sin(double x);
    """)
    m = ffi.load("m")
    x = m.sin(1.23)
    assert x == math.sin(1.23)
