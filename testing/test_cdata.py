import py
from ffi import FFI

class FakeBackend(object):

    def load_library(self):
        return None
    
    def new_primitive_type(self, name):
        return FakePrimitiveType(name)

class FakePrimitiveType(object):

    def __init__(self, cdecl):
        self.cdecl = cdecl


def test_typeof():
    ffi = FFI(backend=FakeBackend())
    clong = ffi.typeof("long")
    assert isinstance(clong, FakePrimitiveType)
    assert clong.cdecl == 'long'

def test_new_array_no_arg():
    ffi = FFI(backend=FakeBackend())
    p = ffi.new("int[10]")
    # the object was zero-initialized:
    for i in range(10):
        assert p[i] == 0

def test_array_indexing():
    ffi = FFI(backend=FakeBackend())
    p = ffi.new("int[10]")
    p[0] = 42
    p[9] = 43
    assert p[0] == 42
    assert p[9] == 43
    py.test.raises(IndexError, "p[10]")
    py.test.raises(IndexError, "p[10] = 44")
    py.test.raises(IndexError, "p[-1]")
    py.test.raises(IndexError, "p[-1] = 44")
