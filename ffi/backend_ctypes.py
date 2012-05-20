import ctypes, ctypes.util
from ffi.backend_base import BackendBase


class CTypesData(object):

    @staticmethod
    def _to_ctypes(value):
        raise TypeError

    @staticmethod
    def _from_ctypes(ctypes_value):
        raise TypeError

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

    @classmethod
    def _get_size(cls):
        return ctypes.sizeof(cls._ctype)

    def _get_size_of_instance(self):
        return ctypes.sizeof(self._ctype)


class CTypesBackend(BackendBase):

    PRIMITIVE_TYPES = {
        'char': ctypes.c_char,
        'short': ctypes.c_short,
        'int': ctypes.c_int,
        'long': ctypes.c_long,
        'long long': ctypes.c_longlong,
        'signed char': ctypes.c_byte,
        'unsigned char': ctypes.c_ubyte,
        'unsigned short': ctypes.c_ushort,
        'unsigned int': ctypes.c_uint,
        'unsigned long': ctypes.c_ulong,
        'unsigned long long': ctypes.c_ulonglong,
        'float': ctypes.c_float,
        'double': ctypes.c_double,
    }

    def load_library(self, name=Ellipsis):
        if name is Ellipsis:
            name = 'c'    # on Posix only
        path = ctypes.util.find_library(name)
        cdll = ctypes.CDLL(path)
        return CTypesLibrary(cdll)

    def new_primitive_type(self, name):
        ctype = self.PRIMITIVE_TYPES[name]
        if name == 'char':
            kind = 'char'
            default_value = '\x00'
        elif name in ('float', 'double'):
            kind = 'float'
            default_value = 0.0
        else:
            kind = 'int'
            default_value = 0
            is_signed = (ctype(-1).value == -1)
        #
        class CTypesPrimitive(CTypesData):
            _ctype = ctype
            _reftypename = '%s &' % name

            def __init__(self, value):
                if value is None:
                    value = default_value
                else:
                    value = CTypesPrimitive._to_ctypes(value)
                self._value = value

            if kind == 'int':
                def __int__(self):
                    return self._value

            if kind == 'char':
                def __int__(self):
                    return ord(self._value)
                def __str__(self):
                    return self._value
                __nonzero__ = __int__
            else:
                def __nonzero__(self):
                    return bool(self._value)

            if kind == 'float':
                def __int__(self):
                    return int(self._value)
                def __float__(self):
                    return self._value

            def __eq__(self, other): return self._value == other
            def __ne__(self, other): return self._value != other
            def __hash__(self):      return hash(self._value)
            def __lt__(self, other): raise TypeError("unorderable type")
            def __le__(self, other): raise TypeError("unorderable type")
            def __gt__(self, other): raise TypeError("unorderable type")
            def __ge__(self, other): raise TypeError("unorderable type")

            if kind == 'int':
                @staticmethod
                def _to_ctypes(x):
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
                            raise OverflowError("%s: integer out of bounds"
                                                % name)
                    return x

            if kind == 'char':
                @staticmethod
                def _to_ctypes(x):
                    if isinstance(x, str) and len(x) == 1:
                        return x
                    if isinstance(x, CTypesPrimitive):    # <CData <char>>
                        return x._value
                    raise TypeError("character expected, got %s" %
                                    type(x).__name__)

            if kind == 'float':
                @staticmethod
                def _to_ctypes(x):
                    if not isinstance(x, (int, long, float, CTypesData)):
                        raise TypeError("float expected, got %s" %
                                        type(x).__name__)
                    return ctype(x).value

            _from_ctypes = staticmethod(_identity)
        #
        CTypesPrimitive._fix_class()
        return CTypesPrimitive

    def new_pointer_type(self, BItem, is_const_charp):
        if is_const_charp:
            kind = 'constcharp'
        elif BItem is self.get_cached_btype('new_primitive_type', 'char'):
            kind = 'charp'
        else:
            kind = 'generic'
        #
        class CTypesPtr(CTypesData):
            _ctype = ctypes.POINTER(BItem._ctype)
            _reftypename = BItem._get_c_name(' * &')

            def __init__(self, init):
                if init is None:
                    address = 0      # null pointer
                elif isinstance(init, CTypesData):
                    address = init._convert_to_address_of(BItem)
                elif kind == 'constcharp' and isinstance(init, str):
                    if '\x00' in init:
                        raise ValueError("string contains \\x00 characters")
                    self._keepalive_string = init
                    address = ctypes.cast(ctypes.c_char_p(init),
                                          ctypes.c_void_p).value
                else:
                    raise TypeError("%r expected, got %r" % (
                        CTypesPtr._get_c_name(), type(init).__name__))
                self._address = address
                self._as_ctype_ptr = ctypes.cast(address, CTypesPtr._ctype)

            def __nonzero__(self):
                return self._address

            def __eq__(self, other):
                return ((isinstance(other, CTypesPtr) and
                         self._address == other._address)
                        or (self._address == 0 and other is None))

            def __ne__(self, other):
                return not self.__eq__(other)

            if kind != 'constcharp':
                def __getitem__(self, index):
                    return BItem._from_ctypes(self._as_ctype_ptr[index])

                def __setitem__(self, index, value):
                    self._as_ctype_ptr[index] = BItem._to_ctypes(value)
            else:
                def __getitem__(self, index):
                    # note that we allow access to the terminating NUL byte
                    if not (0 <= index <= len(self._keepalive_string)):
                        raise IndexError
                    return self._as_ctype_ptr[index]

            if kind == 'charp' or kind == 'constcharp':
                def __str__(self):
                    n = 0
                    while self._as_ctype_ptr[n] != '\x00':
                        n += 1
                    return ''.join([self._as_ctype_ptr[i] for i in range(n)])

            @staticmethod
            def _to_ctypes(value):
                if value is None:
                    address = 0
                else:
                    address = value._convert_to_address_of(BItem)
                return ctypes.cast(address, CTypesPtr._ctype)

            @staticmethod
            def _from_ctypes(ctypes_ptr):
                if not ctypes_ptr:
                    return None
                self = CTypesPtr.__new__(CTypesPtr)
                self._address = ctypes.addressof(ctypes_ptr.contents)
                self._as_ctype_ptr = ctypes_ptr
                return self
        #
        CTypesPtr._fix_class()
        return CTypesPtr

    def new_array_type(self, BItem, length):
        if length is None:
            brackets = ' &[]'
        else:
            brackets = ' &[%d]' % length
        if BItem is self.get_cached_btype('new_primitive_type', 'char'):
            kind = 'char'
        else:
            kind = 'generic'
        #
        class CTypesArray(CTypesData):
            if length is not None:
                _ctype = BItem._ctype * length
            _reftypename = BItem._get_c_name(brackets)

            def __init__(self, init):
                if length is None:
                    if isinstance(init, (int, long)):
                        len1 = init
                        init = None
                    else:
                        init = tuple(init)
                        len1 = len(init)
                    self._ctype = BItem._ctype * len1
                self._blob = self._ctype()
                if init is not None:
                    for i, value in enumerate(init):
                        self[i] = value

            def __len__(self):
                return len(self._blob)

            def __getitem__(self, index):
                if not (0 <= index < len(self._blob)):
                    raise IndexError
                return BItem._from_ctypes(self._blob[index])

            def __setitem__(self, index, value):
                if not (0 <= index < len(self._blob)):
                    raise IndexError
                self._blob[index] = BItem._to_ctypes(value)

            if kind == 'char':
                def __str__(self):
                    return ''.join(self._blob)

            def _convert_to_address_of(self, BClass):
                if BItem is BClass:
                    return ctypes.addressof(self._blob)
                else:
                    return CTypesData._convert_to_address_of(self, BClass)

            @staticmethod
            def _from_ctypes(ctypes_array):
                self = CTypesArray.__new__(CTypesArray)
                self._blob = ctypes_array
                return self
        #
        CTypesArray._fix_class()
        return CTypesArray

    def _new_struct_or_union(self, name, fnames, BFieldTypes,
                             kind, base_ctypes_class, initializer):
        #
        class struct_or_union(base_ctypes_class):
            if fnames is not None:
                _fields_ = [(fname, BField._ctype)
                            for (fname, BField) in zip(fnames, BFieldTypes)]
        struct_or_union.__name__ = '%s_%s' % (kind, name)
        #
        class CTypesStructOrUnion(CTypesData):
            _ctype = struct_or_union
            _reftypename = '%s %s &' % (kind, name)

            def __init__(self, init):
                if fnames is None:
                    raise TypeError("cannot instantiate opaque type %s" % (
                        CTypesStructOrUnion,))
                self._blob = struct_or_union()
                if init is not None:
                    initializer(self, init)
        #
        if fnames is not None:
            for fname, BField in zip(fnames, BFieldTypes):
                if hasattr(CTypesStructOrUnion, fname):
                    raise ValueError("the field name %r conflicts in "
                                     "the ctypes backend" % fname)
                def getter(self, fname=fname, BField=BField):
                    return BField._from_ctypes(getattr(self._blob, fname))
                def setter(self, value, fname=fname, BField=BField):
                    setattr(self._blob, fname, BField._to_ctypes(value))
                setattr(CTypesStructOrUnion, fname, property(getter, setter))
        #
        CTypesStructOrUnion._fix_class()
        return CTypesStructOrUnion

    def new_struct_type(self, name, fnames, BFieldTypes):
        def initializer(self, init):
            init = tuple(init)
            if len(init) > len(fnames):
                raise ValueError("too many values for "
                                 "struct %s initializer" % name)
            for value, fname, BField in zip(init, fnames, BFieldTypes):
                setattr(self._blob, fname, BField._to_ctypes(value))
        return self._new_struct_or_union(name, fnames, BFieldTypes,
                                         'struct', ctypes.Structure,
                                         initializer)

    def new_union_type(self, name, fnames, BFieldTypes):
        def initializer(self, init):
            fname = fnames[0]
            BField = BFieldTypes[0]
            setattr(self._blob, fname, BField._to_ctypes(init))
        return self._new_struct_or_union(name, fnames, BFieldTypes,
                                         'union', ctypes.Union,
                                         initializer)


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
