import py
from cffi1 import FFI
import math


def test_cdef_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a, b; };")
    assert ffi.sizeof("struct foo_s") == 8

def test_cdef_union():
    ffi = FFI()
    ffi.cdef("union foo_s { int a, b; };")
    assert ffi.sizeof("union foo_s") == 4

def test_math_sin():
    py.test.skip("XXX redo!")
    ffi = FFI()
    ffi.cdef("double sin(double);")
    m = ffi.dlopen('m')
    x = m.sin(1.23)
    assert x == math.sin(1.23)
