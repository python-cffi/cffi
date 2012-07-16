import ctypes, ctypes.util, operator
from . import model

class CTypesData(object):
    __slots__ = []

    def __init__(self, *args):
        raise TypeError("cannot instantiate %r" % (self.__class__,))

    @classmethod
    def _newp(cls, init):
        raise TypeError("expected a pointer or array ctype, got '%s'"
                        % (cls._get_c_name(),))

    @staticmethod
    def _to_ctypes(value):
        raise TypeError

    @classmethod
    def _arg_to_ctypes(cls, *value):
        try:
            ctype = cls._ctype
        except AttributeError:
            raise TypeError("cannot create an instance of %r" % (cls,))
        if value:
            res = cls._to_ctypes(*value)
            if not isinstance(res, ctype):
                res = cls._ctype(res)
        else:
            res = cls._ctype()
        return res

    @classmethod
    def _create_ctype_obj(cls, init):
        if init is None:
            return cls._arg_to_ctypes()
        else:
            return cls._arg_to_ctypes(init)

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
        raise NotImplementedError

    def _addr_repr(self, address):
        if address == 0:
            return 'NULL'
        else:
            if address < 0:
                address += 1 << (8*ctypes.sizeof(ctypes.c_void_p))
            return '0x%x' % address

    def __repr__(self, c_name=None):
        own = self._get_own_repr()
        return '<cdata %r %s>' % (c_name or self._get_c_name(), own)

    def _convert_to_address(self, BClass):
        if BClass is None:
            raise TypeError("cannot convert %r to an address" % (
                self._get_c_name(),))
        else:
            raise TypeError("cannot convert %r to %r" % (
                self._get_c_name(), BClass._get_c_name()))

    @classmethod
    def _get_size(cls):
        return ctypes.sizeof(cls._ctype)

    def _get_size_of_instance(self):
        return ctypes.sizeof(self._ctype)

    @classmethod
    def _cast_from(cls, source):
        raise TypeError("cannot cast to %r" % (cls._get_c_name(),))

    def _cast_to_integer(self):
        return self._convert_to_address(None)

    @classmethod
    def _alignment(cls):
        return ctypes.alignment(cls._ctype)

    def __iter__(self):
        raise TypeError("cdata %r does not support iteration" % (
            self._get_c_name()),)

    def _make_cmp(name):
        cmpfunc = getattr(operator, name)
        def cmp(self, other):
            if isinstance(other, CTypesData):
                return cmpfunc(self._convert_to_address(None),
                               other._convert_to_address(None))
            else:
                return NotImplemented
        cmp.func_name = name
        return cmp

    __eq__ = _make_cmp('__eq__')
    __ne__ = _make_cmp('__ne__')
    __lt__ = _make_cmp('__lt__')
    __le__ = _make_cmp('__le__')
    __gt__ = _make_cmp('__gt__')
    __ge__ = _make_cmp('__ge__')

    def __hash__(self):
        return hash(type(self)) ^ hash(self._convert_to_address(None))


class CTypesGenericPrimitive(CTypesData):
    __slots__ = []

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def __hash__(self):
        return object.__hash__(self)

    def _get_own_repr(self):
        return repr(self._from_ctypes(self._value))


class CTypesGenericArray(CTypesData):
    __slots__ = []

    @classmethod
    def _newp(cls, init):
        return cls(init)

    def __iter__(self):
        for i in xrange(len(self)):
            yield self[i]

    def _get_own_repr(self):
        return self._addr_repr(ctypes.addressof(self._blob))


class CTypesGenericPtr(CTypesData):
    __slots__ = ['_address', '_as_ctype_ptr']
    _automatic_casts = False

    @classmethod
    def _newp(cls, init):
        return cls(init)

    @classmethod
    def _cast_from(cls, source):
        if source is None:
            address = 0
        elif isinstance(source, CTypesData):
            address = source._cast_to_integer()
        elif isinstance(source, (int, long)):
            address = source
        else:
            raise TypeError("bad type for cast to %r: %r" %
                            (cls, type(source).__name__))
        return cls._new_pointer_at(address)

    @classmethod
    def _new_pointer_at(cls, address):
        self = cls.__new__(cls)
        self._address = address
        self._as_ctype_ptr = ctypes.cast(address, cls._ctype)
        return self

    def _get_own_repr(self):
        try:
            return self._addr_repr(self._address)
        except AttributeError:
            return '???'

    def _cast_to_integer(self):
        return self._address

    def __nonzero__(self):
        return bool(self._address)

    @classmethod
    def _to_ctypes(cls, value):
        if not isinstance(value, CTypesData):
            raise TypeError("unexpected %s object" % type(value).__name__)
        address = value._convert_to_address(cls)
        return ctypes.cast(address, cls._ctype)

    @classmethod
    def _from_ctypes(cls, ctypes_ptr):
        address = ctypes.cast(ctypes_ptr, ctypes.c_void_p).value or 0
        return cls._new_pointer_at(address)

    @classmethod
    def _initialize(cls, ctypes_ptr, value):
        if value:
            ctypes_ptr.contents = cls._to_ctypes(value).contents

    def _convert_to_address(self, BClass):
        if (BClass in (self.__class__, None) or BClass._automatic_casts
            or self._automatic_casts):
            return self._address
        else:
            return CTypesData._convert_to_address(self, BClass)


class CTypesBaseStructOrUnion(CTypesData):
    __slots__ = ['_blob']

    @classmethod
    def _create_ctype_obj(cls, init):
        # may be overridden
        raise TypeError("cannot instantiate opaque type %s" % (cls,))

    def _get_own_repr(self):
        return self._addr_repr(ctypes.addressof(self._blob))

    @classmethod
    def _offsetof(cls, fieldname):
        return getattr(cls._ctype, fieldname).offset

    def _convert_to_address(self, BClass):
        if getattr(BClass, '_BItem', None) is self.__class__:
            return ctypes.addressof(self._blob)
        else:
            return CTypesData._convert_to_address(self, BClass)

    @classmethod
    def _from_ctypes(cls, ctypes_struct_or_union):
        self = cls.__new__(cls)
        self._blob = ctypes_struct_or_union
        return self

    @classmethod
    def _to_ctypes(cls, value):
        return value._blob

    def __repr__(self, c_name=None):
        return CTypesData.__repr__(self, c_name or self._get_c_name(' &'))


class CTypesBackend(object):

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

    def set_ffi(self, ffi):
        self.ffi = ffi

    def nonstandard_integer_types(self):
        UNSIGNED = 0x1000
        result = {}
        for name in ['long long', 'long', 'int', 'short', 'char']:
            size = ctypes.sizeof(self.PRIMITIVE_TYPES[name])
            result['int%d_t' % (8*size)] = size
            result['uint%d_t' % (8*size)] = size | UNSIGNED
            if size == ctypes.sizeof(ctypes.c_void_p):
                result['intptr_t'] = size
                result['uintptr_t'] = size | UNSIGNED
                result['ptrdiff_t'] = result['intptr_t']
            if size == ctypes.sizeof(ctypes.c_size_t):
                result['size_t'] = size | UNSIGNED
                result['ssize_t'] = size
        return result

    def load_library(self, path):
        cdll = ctypes.CDLL(path)
        return CTypesLibrary(self, cdll)

    def new_void_type(self):
        class CTypesVoid(CTypesData):
            __slots__ = []
            _reftypename = 'void &'
            @staticmethod
            def _from_ctypes(novalue):
                return None
            @staticmethod
            def _to_ctypes(novalue):
                if novalue is not None:
                    raise TypeError("None expected, got %s object" %
                                    (type(novalue).__name__,))
                return None
        CTypesVoid._fix_class()
        return CTypesVoid

    def new_primitive_type(self, name):
        if name == 'wchar_t':
            raise NotImplementedError(name)
        ctype = self.PRIMITIVE_TYPES[name]
        if name == 'char':
            kind = 'char'
        elif name in ('float', 'double'):
            kind = 'float'
        else:
            kind = 'int'
            is_signed = (ctype(-1).value == -1)
        #
        def _cast_source_to_int(source):
            if isinstance(source, (int, long, float)):
                source = int(source)
            elif isinstance(source, CTypesData):
                source = source._cast_to_integer()
            elif isinstance(source, str):
                source = ord(source)
            elif source is None:
                source = 0
            else:
                raise TypeError("bad type for cast to %r: %r" %
                                (CTypesPrimitive, type(source).__name__))
            return source
        #
        class CTypesPrimitive(CTypesGenericPrimitive):
            __slots__ = ['_value']
            _ctype = ctype
            _reftypename = '%s &' % name

            def __init__(self, value):
                self._value = value

            @staticmethod
            def _create_ctype_obj(init):
                if init is None:
                    return ctype()
                return ctype(CTypesPrimitive._to_ctypes(init))

            if kind == 'int':
                @classmethod
                def _cast_from(cls, source):
                    source = _cast_source_to_int(source)
                    source = ctype(source).value     # cast within range
                    return cls(source)
                def __int__(self):
                    return self._value

            if kind == 'char':
                @classmethod
                def _cast_from(cls, source):
                    source = _cast_source_to_int(source)
                    source = chr(source & 0xFF)
                    return cls(source)
                def __int__(self):
                    return ord(self._value)
                def __str__(self):
                    return self._value

            if kind == 'float':
                @classmethod
                def _cast_from(cls, source):
                    if isinstance(source, float):
                        pass
                    elif isinstance(source, CTypesGenericPrimitive):
                        if hasattr(source, '__float__'):
                            source = float(source)
                        else:
                            source = int(source)
                    else:
                        source = _cast_source_to_int(source)
                    source = ctype(source).value     # fix precision
                    return cls(source)
                def __int__(self):
                    return int(self._value)
                def __float__(self):
                    return self._value

            _cast_to_integer = __int__

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
                return getattr(value, 'value', value)

            @staticmethod
            def _initialize(blob, init):
                blob.value = CTypesPrimitive._to_ctypes(init)
        #
        CTypesPrimitive._fix_class()
        return CTypesPrimitive

    def new_pointer_type(self, BItem):
        if BItem is self.ffi._get_cached_btype(model.PrimitiveType('char')):
            kind = 'charp'
        else:
            kind = 'generic'
        #
        class CTypesPtr(CTypesGenericPtr):
            __slots__ = ['_own']
            _BItem = BItem
            if hasattr(BItem, '_ctype'):
                _ctype = ctypes.POINTER(BItem._ctype)
                _bitem_size = ctypes.sizeof(BItem._ctype)
            else:
                _ctype = ctypes.c_void_p
            if issubclass(BItem, CTypesGenericArray):
                _reftypename = BItem._get_c_name('(* &)')
            else:
                _reftypename = BItem._get_c_name(' * &')

            def __init__(self, init):
                ctypeobj = BItem._create_ctype_obj(init)
                self._as_ctype_ptr = ctypes.pointer(ctypeobj)
                self._address = ctypes.cast(self._as_ctype_ptr,
                                            ctypes.c_void_p).value
                self._own = True

            def __add__(self, other):
                if isinstance(other, (int, long)):
                    return self._new_pointer_at(self._address +
                                                other * self._bitem_size)
                else:
                    return NotImplemented

            def __sub__(self, other):
                if isinstance(other, (int, long)):
                    return self._new_pointer_at(self._address -
                                                other * self._bitem_size)
                elif type(self) is type(other):
                    return (self._address - other._address) // self._bitem_size
                else:
                    return NotImplemented

            def __getitem__(self, index):
                if getattr(self, '_own', False) and index != 0:
                    raise IndexError
                return BItem._from_ctypes(self._as_ctype_ptr[index])

            def __setitem__(self, index, value):
                self._as_ctype_ptr[index] = BItem._to_ctypes(value)

            if kind == 'charp':
                def __str__(self):
                    n = 0
                    while self._as_ctype_ptr[n] != '\x00':
                        n += 1
                    return ''.join([self._as_ctype_ptr[i] for i in range(n)])
                @classmethod
                def _arg_to_ctypes(cls, value):
                    if isinstance(value, str):
                        return ctypes.c_char_p(value)
                    else:
                        return super(CTypesPtr, cls)._arg_to_ctypes(value)

            def _get_own_repr(self):
                if getattr(self, '_own', False):
                    return 'owning %d bytes' % (
                        ctypes.sizeof(self._as_ctype_ptr.contents),)
                return super(CTypesPtr, self)._get_own_repr()
        #
        if (BItem is self.ffi._get_cached_btype(model.void_type) or
            BItem is self.ffi._get_cached_btype(model.PrimitiveType('char'))):
            CTypesPtr._automatic_casts = True
        #
        CTypesPtr._fix_class()
        return CTypesPtr

    def new_array_type(self, CTypesPtr, length):
        if length is None:
            brackets = ' &[]'
        else:
            brackets = ' &[%d]' % length
        BItem = CTypesPtr._BItem
        if BItem is self.ffi._get_cached_btype(model.PrimitiveType('char')):
            kind = 'char'
        else:
            kind = 'generic'
        #
        class CTypesArray(CTypesGenericArray):
            __slots__ = ['_blob', '_own']
            if length is not None:
                _ctype = BItem._ctype * length
            else:
                __slots__.append('_ctype')
            _reftypename = BItem._get_c_name(brackets)

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
                    self._initialize(self._blob, init)

            @staticmethod
            def _initialize(blob, init):
                init = tuple(init)
                if len(init) > len(blob):
                    raise IndexError("too many initializers")
                addr = ctypes.cast(blob, ctypes.c_void_p).value
                PTR = ctypes.POINTER(BItem._ctype)
                itemsize = ctypes.sizeof(BItem._ctype)
                for i, value in enumerate(init):
                    p = ctypes.cast(addr + i * itemsize, PTR)
                    BItem._initialize(p.contents, value)

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
                if getattr(self, '_own', False):
                    return 'owning %d bytes' % (ctypes.sizeof(self._blob),)
                return super(CTypesPtr, self)._get_own_repr()

            def _convert_to_address(self, BClass):
                if BClass in (CTypesPtr, None) or BClass._automatic_casts:
                    return ctypes.addressof(self._blob)
                else:
                    return CTypesData._convert_to_address(self, BClass)

            @staticmethod
            def _from_ctypes(ctypes_array):
                self = CTypesArray.__new__(CTypesArray)
                self._blob = ctypes_array
                return self

            @staticmethod
            def _arg_to_ctypes(value):
                return CTypesPtr._arg_to_ctypes(value)

            def __add__(self, other):
                if isinstance(other, (int, long)):
                    return CTypesPtr._new_pointer_at(
                        ctypes.addressof(self._blob) +
                        other * ctypes.sizeof(BItem._ctype))
                else:
                    return NotImplemented
        #
        CTypesArray._fix_class()
        return CTypesArray

    def _new_struct_or_union(self, kind, name, base_ctypes_class):
        #
        class struct_or_union(base_ctypes_class):
            pass
        struct_or_union.__name__ = '%s_%s' % (kind, name)
        #
        class CTypesStructOrUnion(CTypesBaseStructOrUnion):
            __slots__ = ['_blob']
            _ctype = struct_or_union
            _reftypename = '%s %s &' % (kind, name)
            _kind = kind
        #
        CTypesStructOrUnion._fix_class()
        return CTypesStructOrUnion

    def new_struct_type(self, name):
        return self._new_struct_or_union('struct', name, ctypes.Structure)

    def new_union_type(self, name):
        return self._new_struct_or_union('union', name, ctypes.Union)

    def complete_struct_or_union(self, CTypesStructOrUnion, fields, tp):
        struct_or_union = CTypesStructOrUnion._ctype
        fnames = [fname for (fname, BField, bitsize) in fields]
        btypes = [BField for (fname, BField, bitsize) in fields]
        bitfields = [bitsize for (fname, BField, bitsize) in fields]
        #
        cfields = []
        for (fname, BField, bitsize) in fields:
            if bitsize < 0:
                cfields.append((fname, BField._ctype))
            else:
                cfields.append((fname, BField._ctype, bitsize))
        struct_or_union._fields_ = cfields
        #
        @staticmethod
        def _create_ctype_obj(init):
            result = struct_or_union()
            if init is not None:
                initialize(result, init)
            return result
        CTypesStructOrUnion._create_ctype_obj = _create_ctype_obj
        #
        def initialize(blob, init):
            if is_union:
                if len(init) > 1:
                    raise ValueError("union initializer: %d items given, but "
                                    "only one supported (use a dict if needed)"
                                     % (len(init),))
            if not isinstance(init, dict):
                if isinstance(init, str):
                    raise TypeError("union initializer: got a str")
                init = tuple(init)
                if len(init) > len(fnames):
                    raise ValueError("too many values for %s initializer" %
                                     CTypesStructOrUnion._get_c_name())
                init = dict(zip(fnames, init))
            addr = ctypes.addressof(blob)
            for fname, value in init.items():
                BField, bitsize = name2fieldtype[fname]
                assert bitsize < 0, \
                       "not implemented: initializer with bit fields"
                offset = CTypesStructOrUnion._offsetof(fname)
                PTR = ctypes.POINTER(BField._ctype)
                p = ctypes.cast(addr + offset, PTR)
                BField._initialize(p.contents, value)
        is_union = CTypesStructOrUnion._kind == 'union'
        name2fieldtype = dict(zip(fnames, zip(btypes, bitfields)))
        #
        for fname, BField, bitsize in fields:
            if hasattr(CTypesStructOrUnion, fname):
                raise ValueError("the field name %r conflicts in "
                                 "the ctypes backend" % fname)
            if bitsize < 0:
                def getter(self, fname=fname, BField=BField,
                           offset=CTypesStructOrUnion._offsetof(fname),
                           PTR=ctypes.POINTER(BField._ctype)):
                    addr = ctypes.addressof(self._blob)
                    p = ctypes.cast(addr + offset, PTR)
                    return BField._from_ctypes(p.contents)
                def setter(self, value, fname=fname, BField=BField):
                    setattr(self._blob, fname, BField._to_ctypes(value))
            else:
                def getter(self, fname=fname, BField=BField):
                    return BField._from_ctypes(getattr(self._blob, fname))
                def setter(self, value, fname=fname, BField=BField):
                    # xxx obscure workaround
                    value = BField._to_ctypes(value)
                    oldvalue = getattr(self._blob, fname)
                    setattr(self._blob, fname, value)
                    if value != getattr(self._blob, fname):
                        setattr(self._blob, fname, oldvalue)
                        raise OverflowError("value too large for bitfield")
            setattr(CTypesStructOrUnion, fname, property(getter, setter))
        #
        CTypesPtr = self.ffi._get_cached_btype(model.PointerType(tp))
        for fname in fnames:
            if hasattr(CTypesPtr, fname):
                raise ValueError("the field name %r conflicts in "
                                 "the ctypes backend" % fname)
            def getter(self, fname=fname):
                return getattr(self[0], fname)
            def setter(self, value, fname=fname):
                setattr(self[0], fname, value)
            setattr(CTypesPtr, fname, property(getter, setter))

    def new_function_type(self, BArgs, BResult, has_varargs):
        nameargs = [BArg._get_c_name() for BArg in BArgs]
        if has_varargs:
            nameargs.append('...')
        nameargs = ', '.join(nameargs)
        #
        class CTypesFunctionPtr(CTypesGenericPtr):
            __slots__ = ['_own_callback', '_name']
            _ctype = ctypes.CFUNCTYPE(getattr(BResult, '_ctype', None),
                                      *[BArg._ctype for BArg in BArgs],
                                      use_errno=True)
            _reftypename = BResult._get_c_name('(* &)(%s)' % (nameargs,))

            def __init__(self, init, error=None):
                # create a callback to the Python callable init()
                import traceback
                assert not has_varargs, "varargs not supported for callbacks"
                if getattr(BResult, '_ctype', None) is not None:
                    error = BResult._from_ctypes(
                        BResult._create_ctype_obj(error))
                else:
                    error = None
                def callback(*args):
                    args2 = []
                    for arg, BArg in zip(args, BArgs):
                        args2.append(BArg._from_ctypes(arg))
                    try:
                        res2 = init(*args2)
                    except:
                        traceback.print_exc()
                        res2 = error
                    else:
                        res2 = BResult._to_ctypes(res2)
                    if issubclass(BResult, CTypesGenericPtr):
                        if res2:
                            res2 = ctypes.cast(res2, ctypes.c_void_p).value
                                # .value: http://bugs.python.org/issue1574593
                        else:
                            res2 = None
                    #print repr(res2)
                    return res2
                if issubclass(BResult, CTypesGenericPtr):
                    # The only pointers callbacks can return are void*s:
                    # http://bugs.python.org/issue5710
                    callback_ctype = ctypes.CFUNCTYPE(
                        ctypes.c_void_p,
                        *[BArg._ctype for BArg in BArgs],
                        use_errno=True)
                else:
                    callback_ctype = CTypesFunctionPtr._ctype
                self._as_ctype_ptr = callback_ctype(callback)
                self._address = ctypes.cast(self._as_ctype_ptr,
                                            ctypes.c_void_p).value
                self._own_callback = init

            @staticmethod
            def _initialize(ctypes_ptr, value):
                if value:
                    raise NotImplementedError("ctypes backend: not supported: "
                                          "initializers for function pointers")

            def __repr__(self):
                c_name = getattr(self, '_name', None)
                if c_name:
                    i = self._reftypename.index('(* &)')
                    if self._reftypename[i-1] not in ' )*':
                        c_name = ' ' + c_name
                    c_name = self._reftypename.replace('(* &)', c_name)
                return CTypesData.__repr__(self, c_name)

            def _get_own_repr(self):
                if getattr(self, '_own_callback', None) is not None:
                    return 'calling %r' % (self._own_callback,)
                return super(CTypesFunctionPtr, self)._get_own_repr()

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
                        if arg is None:
                            ctypes_args.append(ctypes.c_void_p(0))  # NULL
                            continue
                        if not isinstance(arg, CTypesData):
                            raise TypeError(
                                "argument %d passed in the variadic part "
                                "needs to be a cdata object (got %s)" %
                                (1 + len(BArgs) + i, type(arg).__name__))
                        ctypes_args.append(arg._arg_to_ctypes(arg))
                result = self._as_ctype_ptr(*ctypes_args)
                return BResult._from_ctypes(result)
        #
        CTypesFunctionPtr._fix_class()
        return CTypesFunctionPtr

    def new_enum_type(self, name, enumerators, enumvalues):
        mapping = dict(zip(enumerators, enumvalues))
        reverse_mapping = dict(reversed(zip(enumvalues, enumerators)))
        CTypesInt = self.ffi._get_cached_btype(model.PrimitiveType('int'))
        #
        def forward_map(source):
            if not isinstance(source, str):
                return source
            try:
                return mapping[source]
            except KeyError:
                if source.startswith('#'):
                    try:
                        return int(source[1:])
                    except ValueError:
                        pass
            raise ValueError("%r is not an enumerator for %r" % (
                source, CTypesEnum))
        #
        class CTypesEnum(CTypesInt):
            __slots__ = []
            _reftypename = 'enum %s &' % name

            def __str__(self):
                return str(CTypesEnum._from_ctypes(self._value))

            @classmethod
            def _cast_from(cls, source):
                source = forward_map(source)
                return super(CTypesEnum, cls)._cast_from(source)

            @staticmethod
            def _to_ctypes(x):
                x = forward_map(x)
                return CTypesInt._to_ctypes(x)

            @staticmethod
            def _from_ctypes(value):
                value = CTypesInt._from_ctypes(value)
                try:
                    return reverse_mapping[value]
                except KeyError:
                    return '#%s' % value
        #
        CTypesEnum._fix_class()
        return CTypesEnum

    def get_errno(self):
        return ctypes.get_errno()

    def set_errno(self, value):
        ctypes.set_errno(value)

    def buffer(self, bptr, size=-1):
        # haaaaaaaaaaaack
        call = ctypes.pythonapi.PyBuffer_FromReadWriteMemory
        call.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
        call.restype = ctypes.py_object
        #
        if isinstance(bptr, CTypesGenericPtr):
            if size < 0:
                size = bptr._bitem_size
            return call(bptr._as_ctype_ptr, size)
        elif isinstance(bptr, CTypesGenericArray):
            if size < 0:
                size = ctypes.sizeof(bptr._blob)
            return call(ctypes.pointer(bptr._blob), size)
        else:
            raise TypeError("pointer or array argument expected, got %r" %
                            (type(bptr).__name__,))

    def sizeof(self, cdata_or_BType):
        if isinstance(cdata_or_BType, CTypesData):
            return cdata_or_BType._get_size_of_instance()
        else:
            assert issubclass(cdata_or_BType, CTypesData)
            return cdata_or_BType._get_size()

    def alignof(self, BType):
        assert issubclass(BType, CTypesData)
        return BType._alignment()

    def offsetof(self, BType, fieldname):
        assert issubclass(BType, CTypesData)
        return BType._offsetof(fieldname)

    def newp(self, BType, source):
        return BType._newp(source)

    def cast(self, BType, source):
        return BType._cast_from(source)

    def callback(self, BType, source, error):
        return BType(source, error)

    typeof = type

    def getcname(self, BType, replace_with):
        return BType._get_c_name(replace_with)


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
