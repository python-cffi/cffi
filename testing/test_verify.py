
import py
from ffi import FFI
from platformer import CompilationError

def test_simple_verify():
    ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    py.test.raises(CompilationError, ffi.verify)
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    warns = ffi.verify()
    # warning about lack of inclusion of math.h
    #assert warns is not None --- XXX fix me
    assert ffi.verify('#include <math.h>') is None
