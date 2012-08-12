import weakref

class BaseType(object):

    def get_c_name(self, replace_with=''):
        result = self._get_c_name(replace_with)
        if '$' in result:
            from .ffiplatform import VerificationError
            raise VerificationError(
                "cannot generate '%s' in a C file: unknown type name"
                % (result,))
        return result

    def has_c_name(self):
        return '$' not in self._get_c_name('')

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

    def finish_backend_type(self, ffi):
        return global_cache(ffi, 'new_void_type')

void_type = VoidType()


class PrimitiveType(BaseType):
    _attrs_ = ('name',)

    def __init__(self, name):
        self.name = name

    def _get_c_name(self, replace_with):
        return self.name + replace_with

    def is_char_type(self):
        return self.name in ('char', 'wchar_t')
    def is_signed_type(self):
        return self.is_integer_type() and not self.is_unsigned_type()
    def is_unsigned_type(self):
        return self.name.startswith('unsigned ')
    def is_integer_type(self):
        return not self.is_float_type() and not self.is_char_type()
    def is_float_type(self):
        return self.name in ('double', 'float')

    def finish_backend_type(self, ffi):
        return global_cache(ffi, 'new_primitive_type', self.name)


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

    def finish_backend_type(self, ffi):
        from . import api
        raise api.CDefError("cannot render the type %r: it is a function "
                            "type, not a pointer-to-function type" % (self,))

    def as_function_pointer(self):
        return FunctionPtrType(self.args, self.result, self.ellipsis)


class FunctionPtrType(BaseFunctionType):

    def _get_c_name(self, replace_with):
        return BaseFunctionType._get_c_name(self, '*'+replace_with)

    def finish_backend_type(self, ffi):
        result = ffi._get_cached_btype(self.result)
        args = []
        for tp in self.args:
            args.append(ffi._get_cached_btype(tp))
        return global_cache(ffi, 'new_function_type',
                            tuple(args), result, self.ellipsis)


class PointerType(BaseType):
    _attrs_ = ('totype',)
    
    def __init__(self, totype):
        self.totype = totype

    def _get_c_name(self, replace_with):
        return self.totype._get_c_name('* ' + replace_with)

    def finish_backend_type(self, ffi):
        BItem = ffi._get_cached_btype(self.totype)
        return global_cache(ffi, 'new_pointer_type', BItem)


class ConstPointerType(PointerType):

    def _get_c_name(self, replace_with):
        return self.totype._get_c_name(' const * ' + replace_with)

    def finish_backend_type(self, ffi):
        BPtr = ffi._get_cached_btype(PointerType(self.totype))
        return BPtr


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

    def finish_backend_type(self, ffi):
        BPtrItem = ffi._get_cached_btype(PointerType(self.item))
        return global_cache(ffi, 'new_array_type', BPtrItem, self.length)


class StructOrUnion(BaseType):
    _attrs_ = ('name',)
    forcename = None
    fixedlayout = None

    def __init__(self, name, fldnames, fldtypes, fldbitsize):
        self.name = name
        self.fldnames = fldnames
        self.fldtypes = fldtypes
        self.fldbitsize = fldbitsize

    def _get_c_name(self, replace_with):
        name = self.forcename or '%s %s' % (self.kind, self.name)
        return name + replace_with

    def finish_backend_type(self, ffi):
        BType = self.new_btype(ffi)
        ffi._cached_btypes[self] = BType
        if self.fldtypes is None:
            return BType    # not completing it: it's an opaque struct
        #
        fldtypes = tuple(ffi._get_cached_btype(tp) for tp in self.fldtypes)
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
                    BItemType = ffi._get_cached_btype(ftype.item)
                    nlen, nrest = divmod(fsize, ffi.sizeof(BItemType))
                    if nrest != 0:
                        self._verification_error(
                            "field '%s.%s' has a bogus size?" % (
                            self.name, self.fldnames[i]))
                    ftype = ftype.resolve_length(nlen)
                    self.fldtypes = (self.fldtypes[:i] + (ftype,) +
                                     self.fldtypes[i+1:])
                    BArrayType = ffi._get_cached_btype(ftype)
                    fldtypes = (fldtypes[:i] + (BArrayType,) +
                                fldtypes[i+1:])
                    continue
                #
                bitemsize = ffi.sizeof(fldtypes[i])
                if bitemsize != fsize:
                    self._verification_error(
                        "field '%s.%s' is declared as %d bytes, but is "
                        "really %d bytes" % (self.name, self.fldnames[i],
                                             bitemsize, fsize))
            lst = list(zip(self.fldnames, fldtypes, self.fldbitsize, fieldofs))
            ffi._backend.complete_struct_or_union(BType, lst, self,
                                                  totalsize, totalalignment)
        return BType

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

    def new_btype(self, ffi):
        self.check_not_partial()
        return ffi._backend.new_struct_type(self.name)


class UnionType(StructOrUnion):
    kind = 'union'

    def new_btype(self, ffi):
        return ffi._backend.new_union_type(self.name)


class EnumType(BaseType):
    _attrs_ = ('name',)
    partial = False

    def __init__(self, name, enumerators, enumvalues):
        self.name = name
        self.enumerators = enumerators
        self.enumvalues = enumvalues

    def _get_c_name(self, replace_with):
        return 'enum %s%s' % (self.name, replace_with)

    def check_not_partial(self):
        if self.partial:
            from . import ffiplatform
            raise ffiplatform.VerificationMissing(self._get_c_name(''))

    def finish_backend_type(self, ffi):
        self.check_not_partial()
        return ffi._backend.new_enum_type(self.name, self.enumerators,
                                          self.enumvalues)


def unknown_type(name):
    tp = StructType('$%s' % name, None, None, None)
    tp.forcename = name
    return tp

def global_cache(ffi, funcname, *args):
    try:
        return ffi._backend.__typecache[args]
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
    res = getattr(ffi._backend, funcname)(*args)
    ffi._backend.__typecache[args] = res
    return res
