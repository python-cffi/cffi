import _cffi1_backend

def test_ffi_new():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("int *")
    p[0] = -42
    assert p[0] == -42
