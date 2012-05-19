import ctypes, ctypes.util


class CTypesData(object):

    @staticmethod
    def _import(value):
        x

    @staticmethod
    def _export(ctypes_value):
        raise NotImplementedError


class CTypesBackend(object):

    PRIMITIVE_TYPES = {
        'short': ctypes.c_short,
        'int': ctypes.c_int,
        'long': ctypes.c_long,
        'long long': ctypes.c_longlong,
        'signed char': ctypes.c_byte,
        'signed short': ctypes.c_short,
        'signed': ctypes.c_int,
        'signed long': ctypes.c_long,
        'signed long long': ctypes.c_longlong,
        'unsigned char': ctypes.c_ubyte,
        'unsigned short': ctypes.c_ushort,
        'unsigned': ctypes.c_uint,
        'unsigned long': ctypes.c_ulong,
        'unsigned long long': ctypes.c_ulonglong,
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
        is_signed = (ctype(-1).value == -1)
        #
        class CTypesInt(CTypesData):
            _ctype = ctype

            def __init__(self, value=0):
                if ctype(value).value != value:
                    raise OverflowError("%r out of range: %d" %
                                        (name, value))
                self._value = value

            def __int__(self):
                return self._value

            @staticmethod
            def _import(x):
                if not isinstance(x, (int, long)):
                    if isinstance(x, CTypesData):
                        x = int(x)
                    else:
                        raise TypeError("integer expected, got %s" %
                                        type(x).__name__)
                if ctype(x).value != x:
                    if not is_signed and x < 0:
                        raise OverflowError("%s: negative integer" % name)
                    else:
                        raise OverflowError("%s: integer out of bounds" % name)
                return x
            _export = staticmethod(_identity)
        #
        return CTypesInt

    def new_array_type(self, bitem, length):
        #
        class CTypesArray(CTypesData):
            if length is not None:
                _ctype = bitem._ctype * length

            def __init__(self, init):
                if length is not None:
                    len1 = length
                else:
                    if isinstance(init, (int, long)):
                        len1 = init
                        init = None
                    else:
                        len1 = len(init)
                self._blob = (bitem._ctype * len1)()
                if init is not None:
                    for i, value in enumerate(init):
                        self[i] = value

            def __getitem__(self, index):
                if not (0 <= index < len(self._blob)):
                    raise IndexError
                return bitem._export(self._blob[index])

            def __setitem__(self, index, value):
                if not (0 <= index < len(self._blob)):
                    raise IndexError
                self._blob[index] = bitem._import(value)

            @staticmethod
            def _export(xx):
                xxx
        #
        return CTypesArray


class CTypesLibrary(object):

    def __init__(self, cdll):
        self.cdll = cdll

    def load_function(self, name, bargs, bresult):
        func = getattr(self.cdll, name)
        func.argtypes = [barg._ctype for barg in bargs]
        func.restype = bresult._ctype
        return func


def _identity(x):
    return x
