import ctypes, ctypes.util
from ffi.backend_base import BackendBase


class CTypesData(object):

    @staticmethod
    def _import(value):
        raise NotImplementedError

    @staticmethod
    def _export(ctypes_value):
        raise NotImplementedError

    @classmethod
    def _get_c_name(cls, replace_with=''):
        return cls._reftypename.replace(' &', replace_with)

    @classmethod
    def _fix_class(cls):
        cls.__name__ = 'CData<%s>' % (cls._get_c_name(),)
        cls.__module__ = 'ffi'

    def __repr__(self):
        return '<cdata %r>' % (self._get_c_name(),)

    def _convert_to_address_of(self, BClass):
        raise TypeError("cannot convert %r to %r" % (
            self._get_c_name(), BClass._get_c_name(' *')))


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

            def __init__(self, value):
                if value is None:
                    value = 0
                elif ctype(value).value != value:
                    raise OverflowError("%r out of range: %d" %
                                        (name, value))
                self._value = value

            def __int__(self):
                return self._value

            def __nonzero__(self):   return self._value
            def __lt__(self, other): return self._value <  other
            def __le__(self, other): return self._value <= other
            def __eq__(self, other): return self._value == other
            def __ne__(self, other): return self._value != other
            def __gt__(self, other): return self._value >  other
            def __ge__(self, other): return self._value >= other
            def __hash__(self):      return hash(self._value)

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
        CTypesInt._fix_class()
        return CTypesInt

    def new_pointer_type(self, BItem):
        #
        class CTypesPtr(CTypesData):
            _ctype = ctypes.POINTER(BItem._ctype)
            _reftypename = BItem._get_c_name(' * &')

            def __init__(self, init):
                if init is None:
                    address = 0      # null pointer
                elif isinstance(init, CTypesData):
                    address = init._convert_to_address_of(BItem)
                else:
                    raise TypeError("%r expected, got %r" % (
                        CTypesPtr._get_c_name(), type(init).__name__))
                self._address = address
                self._as_ctype_ptr = ctypes.cast(address, CTypesPtr._ctype)

            @classmethod
            def _from_ctype_ptr(cls, ptr):
                self._address = ctypes.addressof(ptr.contents)
                self._as_ctype_ptr = ptr

            def __nonzero__(self):
                return self._address

            def __eq__(self, other):
                return (isinstance(other, CTypesPtr) and
                        self._address == other._address)

            def __ne__(self, other):
                return not (isinstance(other, CTypesPtr) and
                            self._address == other._address)

            def __getitem__(self, index):
                return BItem._export(self._as_ctype_ptr[index])

            def __setitem__(self, index, value):
                self._as_ctype_ptr[index] = BItem._import(value)
        #
        CTypesPtr._fix_class()
        return CTypesPtr

    def new_array_type(self, BItem, length):
        if length is None:
            brackets = ' &[]'
        else:
            brackets = ' &[%d]' % length
        #
        class CTypesArray(CTypesData):
            if length is not None:
                _ctype = BItem._ctype * length
            _reftypename = BItem._get_c_name(brackets)

            def __init__(self, init):
                if length is not None:
                    len1 = length
                    self._blob = self._ctype()
                else:
                    if isinstance(init, (int, long)):
                        len1 = init
                        init = None
                    else:
                        len1 = len(init)
                    self._blob = (BItem._ctype * len1)()
                if init is not None:
                    for i, value in enumerate(init):
                        self[i] = value

            def __getitem__(self, index):
                if not (0 <= index < len(self._blob)):
                    raise IndexError
                return BItem._export(self._blob[index])

            def __setitem__(self, index, value):
                if not (0 <= index < len(self._blob)):
                    raise IndexError
                self._blob[index] = BItem._import(value)

            def _convert_to_address_of(self, BClass):
                if BItem is BClass:
                    return ctypes.addressof(self._blob)
                else:
                    return CTypesData._convert_to_address_of(self, BClass)

            @staticmethod
            def _export(ctypes_array):
                self = CTypesArray.__new__(CTypesArray)
                self._blob = ctypes_array
                return self
        #
        CTypesArray._fix_class()
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
