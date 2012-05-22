import ctypes, ctypes.util
from ffi.backend_base import BackendBase


class CTypesData(object):

    @staticmethod
    def _to_ctypes(value):
        raise TypeError

    @classmethod
    def _arg_to_ctypes(cls, value):
        res = cls._to_ctypes(value)
        if not isinstance(res, cls._ctype):
            res = cls._ctype(res)
        return res

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

    def _get_own_repr(self):
        return None

    def __repr__(self, c_name=None):
        own = self._get_own_repr()
        if own is None:
            own = ''
        else:
            own = ' owning %s' % (own,)
        return '<cdata %r%s>' % (c_name or self._get_c_name(), own)

    def _convert_to_address_of(self, BClass):
        raise TypeError("cannot convert %r to %r" % (
            self._get_c_name(), BClass._get_c_name(' *')))

    @classmethod
    def _get_size(cls):
        return ctypes.sizeof(cls._ctype)

    def _get_size_of_instance(self):
        return ctypes.sizeof(self._ctype)

    @classmethod
    def _cast_from(cls, source):
        raise TypeError("cannot cast to %r" % (cls._get_c_name(),))

    def _cast_to_integer(self):
        return self._convert_to_address_of(None)


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
            path = None       # the C library
        else:
            if '/' in name:
                path = name
            else:
                path = ctypes.util.find_library(name)
                if path is None:
                    raise OSError("library not found: %r" % (name,))
        cdll = ctypes.CDLL(path)
        return CTypesLibrary(self, cdll)

    def new_void_type(self):
        class CTypesVoid(CTypesData):
            _reftypename = 'void &'
            def __init__(self, value=None):
                raise TypeError("%s cannot be instantiated" % (CTypesVoid,))
            @staticmethod
            def _from_ctypes(novalue):
                return None
        CTypesVoid._fix_class()
        return CTypesVoid

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
                    value = self._to_ctypes(value)
                self._value = value

            @staticmethod
            def _cast_from(source):
                if isinstance(source, (int, long)):
                    pass
                elif isinstance(source, CTypesData):
                    source = source._cast_to_integer()
                elif isinstance(source, str):
                    source = ord(source)
                else:
                    raise TypeError("bad type for cast to %r: %r" %
                                    (CTypesPrimitive, type(source).__name__))
                source = ctype(source).value     # cast within range
                return CTypesPrimitive(source)

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

            _cast_to_integer = __int__

            def __eq__(self, other):
                return (type(self) is type(other) and
                        self._value == other._value)

            def __ne__(self, other):
                return not self.__eq__(other)

            def __hash__(self):
                return hash((CTypesPrimitive, self._value))

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

            @staticmethod
            def _from_ctypes(value):
                return value
        #
        CTypesPrimitive._fix_class()
        return CTypesPrimitive

    def new_pointer_type(self, BItem):
        if BItem is self.get_cached_btype('new_primitive_type', 'char'):
            kind = 'charp'
        else:
            kind = 'generic'
        return self._new_pointer_type(BItem, kind)

    def new_constcharp_type(self):
        BChar = self.get_cached_btype('new_primitive_type', 'char')
        return self._new_pointer_type(BChar, kind='constcharp')

    def _new_pointer_type(self, BItem, kind):
        #
        class CTypesPtr(CTypesData):
            if hasattr(BItem, '_ctype'):
                _ctype = ctypes.POINTER(BItem._ctype)
            else:
                _ctype = ctypes.c_void_p
            if kind != 'constcharp':
                _reftypename = BItem._get_c_name(' * &')
            else:
                _reftypename = 'const char * &'
                _keepalive_string = None

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

            @staticmethod
            def _cast_from(source):
                if source is None:
                    address = 0
                elif isinstance(source, CTypesData):
                    address = source._cast_to_integer()
                elif isinstance(source, (int, long)):
                    address = source
                else:
                    raise TypeError("bad type for cast to %r: %r" %
                                    (CTypesPtr, type(source).__name__))
                self = CTypesPtr.__new__(CTypesPtr)
                self._address = address
                self._as_ctype_ptr = ctypes.cast(address, CTypesPtr._ctype)
                return self

            def _cast_to_integer(self):
                return self._address

            def __nonzero__(self):
                return self._address

            def __eq__(self, other):
                return (type(self) is type(other) and
                        self._address == other._address)

            def __ne__(self, other):
                return not self.__eq__(other)

            def __hash__(self):
                return hash((CTypesPtr, self._address))

            if kind != 'constcharp':
                def __getitem__(self, index):
                    return BItem._from_ctypes(self._as_ctype_ptr[index])

                def __setitem__(self, index, value):
                    self._as_ctype_ptr[index] = BItem._to_ctypes(value)
            else:
                def __getitem__(self, index):
                    # note that we allow access to the terminating NUL byte
                    if index < 0:
                        raise IndexError
                    if (self._keepalive_string is not None and
                            index > len(self._keepalive_string)):
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

            if kind == 'constcharp':
                @classmethod
                def _arg_to_ctypes(cls, value):
                    if isinstance(value, str):
                        return ctypes.c_char_p(value)
                    else:
                        return super(CTypesPtr, cls)._arg_to_ctypes(value)
                def _get_own_repr(self):
                    if self._keepalive_string is not None:
                        return 'a %d-char string' % (
                            len(self._keepalive_string),)
                    return None

            @staticmethod
            def _from_ctypes(ctypes_ptr):
                if not ctypes_ptr:
                    return None
                self = CTypesPtr.__new__(CTypesPtr)
                if self._ctype is ctypes.c_void_p:
                    self._address = ctypes_ptr.value
                else:
                    self._address = ctypes.addressof(ctypes_ptr.contents)
                self._as_ctype_ptr = ctypes_ptr
                return self

            def _convert_to_address_of(self, BClass):
                if BClass in (BItem, CTypesVoid, None):
                    return self._address
                else:
                    return CTypesData._convert_to_address_of(self, BClass)
        #
        CTypesVoid = self.get_cached_btype('new_void_type')
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
            _own = False

            def __init__(self, init):
                if length is None:
                    if isinstance(init, (int, long)):
                        len1 = init
                        init = None
                    else:
                        extra_null = (kind == 'char' and isinstance(init, str))
                        init = tuple(init)
                        len1 = len(init) + extra_null
                    self._ctype = BItem._ctype * len1
                self._blob = self._ctype()
                self._own = True
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
                    s = ''.join(self._blob)
                    try:
                        s = s[:s.index('\x00')]
                    except ValueError:
                        pass
                    return s

            def _get_own_repr(self):
                if self._own:
                    return 'a %d-bytes array' % (ctypes.sizeof(self._blob),)
                return None

            def _convert_to_address_of(self, BClass):
                if BClass in (BItem, CTypesVoid, None):
                    return ctypes.addressof(self._blob)
                else:
                    return CTypesData._convert_to_address_of(self, BClass)

            @staticmethod
            def _from_ctypes(ctypes_array):
                self = CTypesArray.__new__(CTypesArray)
                self._blob = ctypes_array
                return self
        #
        CTypesVoid = self.get_cached_btype('new_void_type')
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
            _own = False

            def __init__(self, init):
                if fnames is None:
                    raise TypeError("cannot instantiate opaque type %s" % (
                        CTypesStructOrUnion,))
                self._blob = struct_or_union()
                self._own = True
                if init is not None:
                    initializer(self, init)

            def _get_own_repr(self):
                if self._own:
                    return '%d bytes' % (ctypes.sizeof(self._blob),)
                return None
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

    def new_function_type(self, BArgs, BResult, has_varargs):
        nameargs = [BArg._get_c_name() for BArg in BArgs]
        if has_varargs:
            nameargs.append('...')
        nameargs = ', '.join(nameargs)
        ctypes_stuff = [BArg._ctype for BArg in BArgs]
        #self.void_type = self.backend.get_cached_btype('new_void_type')
        ctypes_stuff.insert(0, BResult._ctype)
        #
        class CTypesFunction(CTypesData):
            _ctype = ctypes.CFUNCTYPE(*ctypes_stuff, use_errno=True)
            _reftypename = '%s(* &)(%s)' % (BResult._get_c_name(), nameargs)
            _name = None
            _own_callback = None

            def __init__(self, init):
                if init is None:
                    self._ctypes_func = CTypesFunction._ctype(0)
                elif isinstance(init, CTypesFunction):
                    self._ctypes_func = init._ctypes_func
                elif callable(init):
                    # create a callback to the Python callable init()
                    self._ctypes_func = CTypesFunction._ctype(init)
                    self._own_callback = init
                else:
                    raise TypeError("argument must be a callable object")
                self._address = ctypes.cast(self._ctypes_func,
                                            ctypes.c_void_p).value or 0

            @staticmethod
            def _cast_from(source):
                if source is None:
                    address = 0
                elif isinstance(source, CTypesData):
                    address = source._cast_to_integer()
                else:
                    raise TypeError("bad type for cast to %r: %r" %
                                    (CTypesPrimitive, type(source).__name__))
                self = CTypesFunction.__new__(CTypesFunction)
                self._address = address
                self._ctypes_func = ctypes.cast(address, CTypesFunction._ctype)
                return self

            def __nonzero__(self):
                return self._address

            def __eq__(self, other):
                return (type(self) is type(other) and
                        self._address == other._address)

            def __ne__(self, other):
                return not self.__eq__(other)

            def __hash__(self):
                return hash((CTypesFunction, self._address))

            def __repr__(self):
                c_name = self._name
                if c_name:
                    i = self._reftypename.index('(* &)')
                    if self._reftypename[i-1] not in ' )*':
                        c_name = ' ' + c_name
                    c_name = self._reftypename.replace('(* &)', c_name)
                return CTypesData.__repr__(self, c_name)

            def _get_own_repr(self):
                if self._own_callback is not None:
                    return 'a callback to %r' % (self._own_callback,)
                return None

            @staticmethod
            def _from_ctypes(c_func):
                if not c_func:
                    return None
                self = CTypesFunction.__new__(CTypesFunction)
                self._address = ctypes.addressof(c_func)
                self._ctypes_func = ctypes.cast(c_func, CTypesFunction._ctype)
                return self

            def _convert_to_address_of(self, BClass):
                if BClass in (CTypesVoid, None):
                    return self._address
                else:
                    return CTypesData._convert_to_address_of(self, BClass)

            def __call__(self, *args):
                if has_varargs:
                    assert len(args) >= len(BArgs)
                    extraargs = args[len(BArgs):]
                    args = args[:len(BArgs)]
                else:
                    assert len(args) == len(BArgs)
                ctypes_args = []
                for arg, BArg in zip(args, BArgs):
                    ctypes_args.append(BArg._arg_to_ctypes(arg))
                if has_varargs:
                    for i, arg in enumerate(extraargs):
                        if not isinstance(arg, CTypesData):
                            raise TypeError("argument %d needs to be a cdata" %
                                            (1 + len(BArgs) + i,))
                        ctypes_args.append(arg._arg_to_ctypes(arg))
                result = self._ctypes_func(*ctypes_args)
                return BResult._from_ctypes(result)
        #
        CTypesVoid = self.get_cached_btype('new_void_type')
        CTypesFunction._fix_class()
        return CTypesFunction

    def new_enum_type(self, name, enumerators, enumvalues):
        mapping = dict(zip(enumerators, enumvalues))
        CTypesInt = self.get_cached_btype('new_primitive_type', 'int')
        #
        class CTypesEnum(CTypesInt):
            _reftypename = 'enum %s &' % name

            @staticmethod
            def _to_ctypes(x):
                if isinstance(x, str):
                    try:
                        x = mapping[x]
                    except KeyError:
                        raise ValueError("%r is not an enumerator for %r" % (
                            x, CTypesEnum))
                return CTypesInt._to_ctypes(x)

            @staticmethod
            def _from_ctypes(value):
                return enumerators[value]
        #
        CTypesEnum._fix_class()
        return CTypesEnum

    def get_errno(self):
        return ctypes.get_errno()

    def set_errno(self, value):
        ctypes.set_errno(value)


class CTypesLibrary(object):

    def __init__(self, backend, cdll):
        self.backend = backend
        self.cdll = cdll

    def load_function(self, BType, name):
        c_func = getattr(self.cdll, name)
        funcobj = BType._from_ctypes(c_func)
        funcobj._name = name
        return funcobj

    def read_variable(self, BType, name):
        ctypes_obj = BType._ctype.in_dll(self.cdll, name)
        return BType._from_ctypes(ctypes_obj)

    def write_variable(self, BType, name, value):
        new_ctypes_obj = BType._to_ctypes(value)
        ctypes_obj = BType._ctype.in_dll(self.cdll, name)
        ctypes.memmove(ctypes.addressof(ctypes_obj),
                       ctypes.addressof(new_ctypes_obj),
                       ctypes.sizeof(BType._ctype))
