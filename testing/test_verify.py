
import py
from ffi import FFI
from platformer import CompilationError

def test_simple_verify():
    ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    py.test.raises(CompilationError, ffi.verify)
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    py.test.raises(CompilationError, ffi.verify)
    # omission of math.h
    assert ffi.verify('#include <math.h>') is None
