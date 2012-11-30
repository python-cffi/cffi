import weakref

class BaseType(object):

    def get_c_name(self, replace_with='', context='a C file'):
        result = self._get_c_name(replace_with)
        if '$' in result:
            from .ffiplatform import VerificationError
            raise VerificationError(
                "cannot generate '%s' in %s: unknown type name"
                % (self._get_c_name(''), context))
        return result

    def has_c_name(self):
        return '$' not in self._get_c_name('')

    def get_cached_btype(self, ffi, finishlist, can_delay=False):
        try:
            BType = ffi._cached_btypes[self]
        except KeyError:
            BType = self.build_backend_type(ffi, finishlist)
            BType2 = ffi._cached_btypes.setdefault(self, BType)
            assert BType2 is BType
        return BType

    def __repr__(self):
        return '<%s>' % (self._get_c_name(''),)

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self._get_items() == other._get_items())

    def __ne__(self, other):
        return not self == other

    def _get_items(self):
        return [(name, getattr(self, name)) for name in self._attrs_]

    def __hash__(self):
        return hash((self.__class__, tuple(self._get_items())))


class VoidType(BaseType):
    _attrs_ = ()

    def _get_c_name(self, replace_with):
        return 'void' + replace_with

    def build_backend_type(self, ffi, finishlist):
        return global_cache(self, ffi, 'new_void_type')

void_type = VoidType()


class PrimitiveType(BaseType):
    _attrs_ = ('name',)

    ALL_PRIMITIVE_TYPES = {
        'char':               'c',
        'short':              'i',
        'int':                'i',
        'long':               'i',
        'long long':          'i',
        'signed char':        'i',
        'unsigned char':      'u',
        'unsigned short':     'u',
        'unsigned int':       'u',
        'unsigned long':      'u',
        'unsigned long long': 'u',
        'float':              'f',
        'double':             'f',
        'long double':        'f',
        'wchar_t':            'c',
        '_Bool':              'u',
        # the following types are not primitive in the C sense
        'int8_t':             'i',
        'uint8_t':            'u',
        'int16_t':            'i',
        'uint16_t':           'u',
        'int32_t':            'i',
        'uint32_t':           'u',
        'int64_t':            'i',
        'uint64_t':           'u',
        'intptr_t':           'i',
        'uintptr_t':          'u',
        'ptrdiff_t':          'i',
        'size_t':             'u',
        'ssize_t':            'i',
        }

    def __init__(self, name):
        assert name in self.ALL_PRIMITIVE_TYPES
        self.name = name

    def _get_c_name(self, replace_with):
        return self.name + replace_with

    def is_char_type(self):
        return self.ALL_PRIMITIVE_TYPES[self.name] == 'c'
    def is_signed_type(self):
        return self.ALL_PRIMITIVE_TYPES[self.name] == 'i'
    def is_unsigned_type(self):
        return self.ALL_PRIMITIVE_TYPES[self.name] == 'u'
    def is_integer_type(self):
        return self.ALL_PRIMITIVE_TYPES[self.name] in 'iu'
    def is_float_type(self):
        return self.ALL_PRIMITIVE_TYPES[self.name] == 'f'

    def build_backend_type(self, ffi, finishlist):
        return global_cache(self, ffi, 'new_primitive_type', self.name)


class BaseFunctionType(BaseType):
    _attrs_ = ('args', 'result', 'ellipsis')

    def __init__(self, args, result, ellipsis):
        self.args = args
        self.result = result
        self.ellipsis = ellipsis

    def _get_c_name(self, replace_with):
        reprargs = [arg._get_c_name('') for arg in self.args]
        if self.ellipsis:
            reprargs.append('...')
        reprargs = reprargs or ['void']
        replace_with = '(%s)(%s)' % (replace_with, ', '.join(reprargs))
        return self.result._get_c_name(replace_with)


class RawFunctionType(BaseFunctionType):
    # Corresponds to a C type like 'int(int)', which is the C type of
    # a function, but not a pointer-to-function.  The backend has no
    # notion of such a type; it's used temporarily by parsing.

    def build_backend_type(self, ffi, finishlist):
        from . import api
        raise api.CDefError("cannot render the type %r: it is a function "
                            "type, not a pointer-to-function type" % (self,))

    def as_function_pointer(self):
        return FunctionPtrType(self.args, self.result, self.ellipsis)


class FunctionPtrType(BaseFunctionType):

    def _get_c_name(self, replace_with):
        return BaseFunctionType._get_c_name(self, '*'+replace_with)

    def build_backend_type(self, ffi, finishlist):
        result = self.result.get_cached_btype(ffi, finishlist)
        args = []
        for tp in self.args:
            args.append(tp.get_cached_btype(ffi, finishlist))
        return global_cache(self, ffi, 'new_function_type',
                            tuple(args), result, self.ellipsis)


class PointerType(BaseType):
    _attrs_ = ('totype',)
    
    def __init__(self, totype):
        self.totype = totype

    def _get_c_name(self, replace_with):
        return self.totype._get_c_name('* ' + replace_with)

    def build_backend_type(self, ffi, finishlist):
        BItem = self.totype.get_cached_btype(ffi, finishlist, can_delay=True)
        return global_cache(self, ffi, 'new_pointer_type', BItem)

voidp_type = PointerType(void_type)


class ConstPointerType(PointerType):

    def _get_c_name(self, replace_with):
        return self.totype._get_c_name(' const * ' + replace_with)

    def build_backend_type(self, ffi, finishlist):
        BPtr = PointerType(self.totype).get_cached_btype(ffi, finishlist)
        return BPtr


class NamedPointerType(PointerType):
    _attrs_ = ('totype', 'name')

    def __init__(self, totype, name):
        PointerType.__init__(self, totype)
        self.name = name

    def _get_c_name(self, replace_with):
        return self.name + replace_with


class ArrayType(BaseType):
    _attrs_ = ('item', 'length')

    def __init__(self, item, length):
        self.item = item
        self.length = length

    def resolve_length(self, newlength):
        return ArrayType(self.item, newlength)

    def _get_c_name(self, replace_with):
        if self.length is None:
            brackets = '[]'
        else:
            brackets = '[%d]' % self.length
        return self.item._get_c_name(replace_with + brackets)

    def build_backend_type(self, ffi, finishlist):
        self.item.get_cached_btype(ffi, finishlist)   # force the item BType
        BPtrItem = PointerType(self.item).get_cached_btype(ffi, finishlist)
        return global_cache(self, ffi, 'new_array_type', BPtrItem, self.length)


class StructOrUnionOrEnum(BaseType):
    _attrs_ = ('name',)
    forcename = None

    def _get_c_name(self, replace_with):
        name = self.forcename or '%s %s' % (self.kind, self.name)
        return name + replace_with


class StructOrUnion(StructOrUnionOrEnum):
    fixedlayout = None
    completed = False

    def __init__(self, name, fldnames, fldtypes, fldbitsize):
        self.name = name
        self.fldnames = fldnames
        self.fldtypes = fldtypes
        self.fldbitsize = fldbitsize

    def enumfields(self):
        for name, type, bitsize in zip(self.fldnames, self.fldtypes,
                                       self.fldbitsize):
            if name == '' and isinstance(type, StructOrUnion):
                # nested anonymous struct/union
                for result in type.enumfields():
                    yield result
            else:
                yield (name, type, bitsize)

    def force_flatten(self):
        # force the struct or union to have a declaration that lists
        # directly all fields returned by enumfields(), flattening
        # nested anonymous structs/unions.
        names = []
        types = []
        bitsizes = []
        for name, type, bitsize in self.enumfields():
            names.append(name)
            types.append(type)
            bitsizes.append(bitsize)
        self.fldnames = tuple(names)
        self.fldtypes = tuple(types)
        self.fldbitsize = tuple(bitsizes)

    def get_cached_btype(self, ffi, finishlist, can_delay=False):
        BType = StructOrUnionOrEnum.get_cached_btype(self, ffi, finishlist,
                                                     can_delay)
        if not can_delay:
            self.finish_backend_type(ffi, finishlist)
        return BType

    def finish_backend_type(self, ffi, finishlist):
        if self.completed:
            if self.completed != 2:
                raise NotImplementedError("recursive structure declaration "
                                          "for '%s'" % (self.name,))
            return
        BType = ffi._cached_btypes[self]
        if self.fldtypes is None:
            return    # not completing it: it's an opaque struct
        #
        self.completed = 1
        fldtypes = tuple(tp.get_cached_btype(ffi, finishlist)
                         for tp in self.fldtypes)
        #
        if self.fixedlayout is None:
            lst = list(zip(self.fldnames, fldtypes, self.fldbitsize))
            ffi._backend.complete_struct_or_union(BType, lst, self)
            #
        else:
            fieldofs, fieldsize, totalsize, totalalignment = self.fixedlayout
            for i in range(len(self.fldnames)):
                fsize = fieldsize[i]
                ftype = self.fldtypes[i]
                #
                if isinstance(ftype, ArrayType) and ftype.length is None:
                    # fix the length to match the total size
                    BItemType = ftype.item.get_cached_btype(ffi, finishlist)
                    nlen, nrest = divmod(fsize, ffi.sizeof(BItemType))
                    if nrest != 0:
                        self._verification_error(
                            "field '%s.%s' has a bogus size?" % (
                            self.name, self.fldnames[i] or '{}'))
                    ftype = ftype.resolve_length(nlen)
                    self.fldtypes = (self.fldtypes[:i] + (ftype,) +
                                     self.fldtypes[i+1:])
                    BArrayType = ftype.get_cached_btype(ffi, finishlist)
                    fldtypes = (fldtypes[:i] + (BArrayType,) +
                                fldtypes[i+1:])
                    continue
                #
                bitemsize = ffi.sizeof(fldtypes[i])
                if bitemsize != fsize:
                    self._verification_error(
                        "field '%s.%s' is declared as %d bytes, but is "
                        "really %d bytes" % (self.name,
                                             self.fldnames[i] or '{}',
                                             bitemsize, fsize))
            lst = list(zip(self.fldnames, fldtypes, self.fldbitsize, fieldofs))
            ffi._backend.complete_struct_or_union(BType, lst, self,
                                                  totalsize, totalalignment)
        self.completed = 2

    def _verification_error(self, msg):
        from .ffiplatform import VerificationError
        raise VerificationError(msg)


class StructType(StructOrUnion):
    kind = 'struct'
    partial = False

    def check_not_partial(self):
        if self.partial and self.fixedlayout is None:
            from . import ffiplatform
            raise ffiplatform.VerificationMissing(self._get_c_name(''))

    def build_backend_type(self, ffi, finishlist):
        self.check_not_partial()
        finishlist.append(self)
        return ffi._backend.new_struct_type(self.name)


class UnionType(StructOrUnion):
    kind = 'union'

    def build_backend_type(self, ffi, finishlist):
        finishlist.append(self)
        return ffi._backend.new_union_type(self.name)


class EnumType(StructOrUnionOrEnum):
    kind = 'enum'
    partial = False
    partial_resolved = False

    def __init__(self, name, enumerators, enumvalues):
        self.name = name
        self.enumerators = enumerators
        self.enumvalues = enumvalues

    def check_not_partial(self):
        if self.partial and not self.partial_resolved:
            from . import ffiplatform
            raise ffiplatform.VerificationMissing(self._get_c_name(''))

    def build_backend_type(self, ffi, finishlist):
        self.check_not_partial()
        return ffi._backend.new_enum_type(self.name, self.enumerators,
                                          self.enumvalues)


def unknown_type(name, structname=None):
    if structname is None:
        structname = '$%s' % name
    tp = StructType(structname, None, None, None)
    tp.forcename = name
    return tp

def unknown_ptr_type(name, structname=None):
    if structname is None:
        structname = '*$%s' % name
    tp = StructType(structname, None, None, None)
    return NamedPointerType(tp, name)

file_type = unknown_type('FILE', '_IO_FILE')

def global_cache(srctype, ffi, funcname, *args):
    key = (funcname, args)
    try:
        return ffi._backend.__typecache[key]
    except KeyError:
        pass
    except AttributeError:
        # initialize the __typecache attribute, either at the module level
        # if ffi._backend is a module, or at the class level if ffi._backend
        # is some instance.
        ModuleType = type(weakref)
        if isinstance(ffi._backend, ModuleType):
            ffi._backend.__typecache = weakref.WeakValueDictionary()
        else:
            type(ffi._backend).__typecache = weakref.WeakValueDictionary()
    try:
        res = getattr(ffi._backend, funcname)(*args)
    except NotImplementedError as e:
        raise NotImplementedError("%r: %s" % (srctype, e))
    ffi._backend.__typecache[key] = res
    return res

def pointer_cache(ffi, BType):
    return global_cache('?', ffi, 'new_pointer_type', BType)

def attach_exception_info(e, name):
    if e.args and type(e.args[0]) is str:
        e.args = ('%s: %s' % (name, e.args[0]),) + e.args[1:]
