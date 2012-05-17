import ctypes, ctypes.util


class CTypesBackend(object):

    PRIMITIVE_TYPES = {
        'int': ctypes.c_int,
        'double': ctypes.c_double,
    }

    def load_library(self, name=Ellipsis):
        if name is Ellipsis:
            name = 'c'    # on Posix only
        path = ctypes.util.find_library(name)
        cdll = ctypes.CDLL(path)
        return CTypesLibrary(cdll)

    def new_primitive_type(self, name):
        return self.PRIMITIVE_TYPES[name]

    def new_array_type(self, bitem, length):
        ctype = bitem * length
        #
        class CTypesArray(object):
            def __init__(self):
                self._blob = ctype()
            def __getitem__(self, index):
                if not (0 <= index < length):
                    raise IndexError
                return self._blob[index]
            def __setitem__(self, index, value):
                if not (0 <= index < length):
                    raise IndexError
                self._blob[index] = value
        #
        return CTypesArray


class CTypesLibrary(object):

    def __init__(self, cdll):
        self.cdll = cdll

    def load_function(self, name, args, result):
        func = getattr(self.cdll, name)
        func.argtypes = args
        func.restype = result
        return func
