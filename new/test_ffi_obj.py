import py
import _cffi1_backend


def test_ffi_new():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("int *")
    p[0] = -42
    assert p[0] == -42

def test_ffi_subclass():
    class FOO(_cffi1_backend.FFI):
        def __init__(self, x):
            self.x = x
    foo = FOO(42)
    assert foo.x == 42
    p = foo.new("int *")
    assert p[0] == 0

def test_ffi_no_argument():
    py.test.raises(TypeError, _cffi1_backend.FFI, 42)
