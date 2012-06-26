import py
from cffi import FFI

class FakeBackend(object):

    def nonstandard_integer_types(self):
        return {}

    def sizeof(self, name):
        return 1

    def load_library(self, path):
        return "fake library"

    def new_primitive_type(self, name):
        return FakePrimitiveType(name)

    def new_void_type(self):
        return "void!"
    def new_pointer_type(self, x):
        return 'ptr-to-%r!' % (x,)
    def cast(self, x, y):
        return 'casted!'

class FakePrimitiveType(object):

    def __init__(self, cdecl):
        self.cdecl = cdecl


def test_typeof():
    ffi = FFI(backend=FakeBackend())
    clong = ffi.typeof("signed long int")
    assert isinstance(clong, FakePrimitiveType)
    assert clong.cdecl == 'long'
