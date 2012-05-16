import ctypes


class CTypesBackend(object):

    PRIMITIVE_TYPES = {
        'double': ctypes.c_double,
    }

    def load_library(self, name):
        cdll = ctypes.CDLL('lib%s.so' % name)
        return CTypesLibrary(cdll)

    def new_primitive_type(self, name):
        return self.PRIMITIVE_TYPES[name]


class CTypesLibrary(object):

    def __init__(self, cdll):
        self.cdll = cdll

    def load_function(self, name, args, result):
        func = getattr(self.cdll, name)
        func.argtypes = args
        func.restype = result
        return func
