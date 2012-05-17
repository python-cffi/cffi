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
