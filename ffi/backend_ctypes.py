import ctypes, ctypes.util
from ffi.backend_base import BackendBase


class CTypesData(object):

    @staticmethod
    def _import(value):
        x

    @staticmethod
    def _export(ctypes_value):
        raise NotImplementedError

    @classmethod
    def _get_c_name(cls):
        return cls._reftypename.replace(' &', '')

    def __repr__(self):
        return '<cdata %r>' % (self._get_c_name(),)

    def _cast_to_address_of(self, Class):
        raise TypeError("cannot cast %r to %r" % (
            self._get_c_name(), Class._reftypename.replace('&', '*')))


class CTypesBackend(BackendBase):

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
            _reftypename = '%s &' % name

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

    def new_pointer_type(self, bitem):
        #
        class CTypesPtr(CTypesData):
            _ctype = ctypes.POINTER(bitem._ctype)
            _reftypename = bitem._reftypename.replace('&', '* &')

            def __init__(self, init):
                if init is None:
                    address = 0      # null pointer
                elif isinstance(init, CTypesData):
                    address = init._cast_to_address_of(bitem)
                else:
                    raise TypeError("%r expected, got %r" % (
                        CTypesPtr._get_c_name(), type(init).__name__))
                self._address = ctypes.cast(address, self._ctype)

            def __getitem__(self, index):
                return bitem._export(self._address[index])

            def __setitem__(self, index, value):
                self._address[index] = bitem._import(value)
        #
        return CTypesPtr

    def new_array_type(self, bitem, length):
        if length is None:
            brackets = '[] &'
        else:
            brackets = '[%d] &' % length
        reftypename = bitem._reftypename.replace(' &', brackets)
        #
        class CTypesArray(CTypesData):
            if length is not None:
                _ctype = bitem._ctype * length
            _reftypename = reftypename

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

            def _cast_to_address_of(self, bexpecteditem):
                if bitem is bexpecteditem:
                    return ctypes.addressof(self._blob)
                else:
                    return CTypesData._cast_to_address_of(self, bexpecteditem)
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
