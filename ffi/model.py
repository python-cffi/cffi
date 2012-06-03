
class BaseType(object):
    pass

class PrimitiveType(BaseType):
    def __init__(self, name):
        self.name = name

    def new_backend_type(self, backend):
        return backend.new_primitive_type(self.name)

    # def __hash__(self):
    #     return hash(self.name)

    # def __eq__(self, other):
    #     if self.__class__ != other.__class__:
    #         return False
    #     return self.name == other.name

    # def __ne__(self, other):
    #     return not self == other

class FunctionType(BaseType):
    pass

class PointerType(BaseType):
    def __init__(self, totype):
        self.totype = totype

    def new_backend_type(self, backend):
        return backend.new_pointer_type(self.totype.new_backend_type(backend))
