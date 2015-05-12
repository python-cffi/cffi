import py
from cffi import FFI
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
