import py
from cffi1 import FFI
import math


def test_math_sin():
    py.test.skip("XXX redo!")
    ffi = FFI()
    ffi.cdef("double sin(double);")
    m = ffi.dlopen('m')
    x = m.sin(1.23)
    assert x == math.sin(1.23)
