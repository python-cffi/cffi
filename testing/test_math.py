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
