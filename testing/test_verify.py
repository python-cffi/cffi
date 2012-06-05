
import py
from cffi import FFI
from platformer import CompilationError

def test_simple_verify():
    ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    py.test.raises(CompilationError, ffi.verify)
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    # omission of math.h
    py.test.raises(CompilationError, ffi.verify)
    assert ffi.verify('#include <math.h>') is None
