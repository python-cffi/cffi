import py
from cffi import FFI, VerificationError

def test_simple_verify():
    ffi = FFI()
    ffi.cdef("void some_completely_unknown_function();")
    py.test.raises(VerificationError, ffi.verify)
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    # omission of math.h
    py.test.raises(VerificationError, ffi.verify)
    assert ffi.verify('#include <math.h>') is None
    #
    ffi = FFI()
    ffi.cdef("float sin(double x);")
    py.test.raises(VerificationError, ffi.verify, '#include <math.h>')
    ffi = FFI()
    ffi.cdef("double sin(float x);")
    py.test.raises(VerificationError, ffi.verify, '#include <math.h>')
