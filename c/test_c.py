import py
import _ffi_backend


def test_load_library():
    x = _ffi_backend.load_library("libc.so.6")     # Linux only
    assert repr(x).startswith("<_ffi_backend.Library object at 0x")

def test_nonstandard_integer_types():
    d = _ffi_backend.nonstandard_integer_types()
    assert type(d) is dict
    assert 'char' not in d
    assert d['size_t'] in (0x1004, 0x1008)
    assert d['size_t'] == d['ssize_t'] + 0x1000

def test_new_primitive_type():
    py.test.raises(KeyError, _ffi_backend.new_primitive_type, None, "foo")
    p = _ffi_backend.new_primitive_type(None, "signed char")
    assert repr(p) == "<ctypedescr 'signed char'>"
