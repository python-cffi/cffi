import ctypes, ctypes.util


class CTypesBackend(object):

    PRIMITIVE_TYPES = {
        'short': ctypes.c_short,
        'int': ctypes.c_int,
        'long': ctypes.c_long,
        'long int': ctypes.c_long,
        'long long': ctypes.c_longlong,
        'long long int': ctypes.c_longlong,
        'signed char': ctypes.c_byte,
        'signed short': ctypes.c_short,
        'signed int': ctypes.c_int,
        'signed long': ctypes.c_long,
        'signed long int': ctypes.c_long,
        'signed long long': ctypes.c_longlong,
        'signed long long int': ctypes.c_longlong,
        'unsigned char': ctypes.c_ubyte,
        'unsigned short': ctypes.c_ushort,
        'unsigned int': ctypes.c_uint,
        'unsigned long': ctypes.c_ulong,
        'unsigned long int': ctypes.c_ulong,
        'unsigned long long': ctypes.c_ulonglong,
        'unsigned long long int': ctypes.c_ulonglong,
        'double': ctypes.c_double,
    }

    def load_library(self, name=Ellipsis):
        if name is Ellipsis:
            name = 'c'    # on Posix only
        path = ctypes.util.find_library(name)
        cdll = ctypes.CDLL(path)
        return CTypesLibrary(cdll)

    def new_primitive_type(self, name):
        # XXX integer types only
        ctype = self.PRIMITIVE_TYPES[name]
        #
        class CTypesInt(object):
            _ctype = ctype
            def __init__(self, value=0):
                if ctype(value).value != value:
                    raise OverflowError("%r out of range: %d" %
                                        (name, value))
                self._value = value
            def __int__(self):
                return self._value
        #
        return CTypesInt

    def new_array_type(self, bitem, length):
        ctype = bitem._ctype * length
        #
        class CTypesArray(object):
            def __init__(self, *args):
                if len(args) > length:
                    raise TypeError("too many arguments: expected up to %d, "
                                    "got %d" % (length, len(args)))
                self._blob = ctype()
                for i, value in enumerate(args):
                    self[i] = value
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
