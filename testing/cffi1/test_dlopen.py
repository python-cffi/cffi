import py
from cffi import FFI, VerificationError
from cffi.recompiler import make_py_source
from testing.udir import udir


def test_simple():
    ffi = FFI()
    ffi.cdef("int close(int); static const int BB = 42;")
    target = udir.join('test_simple.py')
    assert make_py_source(ffi, 'test_simple', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_simple',
    _types = b'\x00\x00\x01\x0D\x00\x00\x07\x01\x00\x00\x00\x0F',
    _globals = (b'\xFF\xFF\xFF\x1FBB',42,b'\x00\x00\x00\x23close',0),
)
"""

def test_invalid_global_constant():
    ffi = FFI()
    ffi.cdef("static const int BB;")
    target = udir.join('test_invalid_global_constants.py')
    e = py.test.raises(VerificationError, make_py_source, ffi,
                       'test_invalid_global_constants', str(target))
    assert str(e.value) == (
        "ffi.dlopen() will not be able to figure out "
        "the value of constant 'BB' (only integer constants are "
        "supported, and only if their value are specified in the cdef)")

def test_invalid_dotdotdot_in_macro():
    ffi = FFI()
    ffi.cdef("#define FOO ...")
    target = udir.join('test_invalid_dotdotdot_in_macro.py')
    e = py.test.raises(VerificationError, make_py_source, ffi,
                       'test_invalid_dotdotdot_in_macro', str(target))
    assert str(e.value) == (
        "ffi.dlopen() will not be able to figure out "
        "the value of constant 'FOO' (only integer constants are "
        "supported, and only if their value are specified in the cdef)")
