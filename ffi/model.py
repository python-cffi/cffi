
class BaseType(object):
    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.__dict__ == other.__dict__)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        items = self.__dict__.items()
        items.sort()
        return hash((self.__class__, tuple(items)))

    def get_backend_type(self, ffi):
        return ffi._get_cached_btype(self)

class VoidType(BaseType):
    def new_backend_type(self, ffi):
        return ffi._backend.new_void_type()

void_type = VoidType()

class PrimitiveType(BaseType):
    def __init__(self, name):
        self.name = name

    def new_backend_type(self, ffi):
        return ffi._backend.new_primitive_type(self.name)

class FunctionType(BaseType):
    pass

class PointerType(BaseType):
    def __init__(self, totype):
        self.totype = totype

    def new_backend_type(self, ffi):
        return ffi._backend.new_pointer_type(ffi._get_cached_btype(self.totype))
