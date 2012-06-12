
class BaseType(object):

    def __repr__(self):
        return '<%s>' % (self.get_c_name(),)

    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self._get_items() == other._get_items())

    def __ne__(self, other):
        return not self == other

    def _get_items(self):
        return [(name, getattr(self, name)) for name in self._attrs_]

    def __hash__(self):
        return hash((self.__class__, tuple(self._get_items())))

    def prepare_backend_type(self, ffi):
        pass

    def finish_backend_type(self, ffi, *args):
        try:
            return ffi._cached_btypes[self]
        except KeyError:
            return self.new_backend_type(ffi, *args)

    def verifier_declare_typedef(self, verifier, name):
        verifier.write('{ %s = (%s**)0; }' % (
            self.get_c_name('** result'), name))


class VoidType(BaseType):
    _attrs_ = ()

    def get_c_name(self, replace_with=''):
        return 'void' + replace_with

    def new_backend_type(self, ffi):
        return ffi._backend.new_void_type()

void_type = VoidType()

class PrimitiveType(BaseType):
    _attrs_ = ('name',)

    def __init__(self, name):
        self.name = name

    def get_c_name(self, replace_with=''):
        return self.name + replace_with

    def new_backend_type(self, ffi):
        return ffi._backend.new_primitive_type(self.name)

class FunctionType(BaseType):
    _attrs_ = ('args', 'result', 'ellipsis')

    def __init__(self, args, result, ellipsis):
        self.args = args
        self.result = result
        self.ellipsis = ellipsis

    def get_c_name(self, replace_with=''):
        reprargs = [arg.get_c_name() for arg in self.args]
        if self.ellipsis:
            reprargs.append('...')
        reprargs = reprargs or ['void']
        replace_with = '(*%s)(%s)' % (replace_with, ', '.join(reprargs))
        return self.result.get_c_name(replace_with)

    def prepare_backend_type(self, ffi):
        args = [ffi._get_cached_btype(self.result)]
        for tp in self.args:
            args.append(ffi._get_cached_btype(tp))
        return args

    def new_backend_type(self, ffi, result, *args):
        return ffi._backend.new_function_type(args, result, self.ellipsis)

    def verifier_declare_function(self, verifier, name):
        verifier.write('{ %s = %s; }' % (
            self.get_c_name('result'), name))


class PointerType(BaseType):
    _attrs_ = ('totype',)
    
    def __init__(self, totype):
        self.totype = totype

    def get_c_name(self, replace_with=''):
        return self.totype.get_c_name('* ' + replace_with)

    def prepare_backend_type(self, ffi):
        return (ffi._get_cached_btype(self.totype),)

    def new_backend_type(self, ffi, BItem):
        return ffi._backend.new_pointer_type(BItem)

class ConstPointerType(PointerType):

    def get_c_name(self, replace_with=''):
        return self.totype.get_c_name(' const * ' + replace_with)

    def prepare_backend_type(self, ffi):
        return (ffi._get_cached_btype(PointerType(self.totype)),)

    def new_backend_type(self, ffi, BPtr):
        return BPtr


class ArrayType(BaseType):
    _attrs_ = ('item', 'length')

    def __init__(self, item, length):
        self.item = item
        self.length = length

    def get_c_name(self, replace_with=''):
        if self.length is None:
            brackets = '[]'
        else:
            brackets = '[%d]' % self.length
        return self.item.get_c_name(replace_with + brackets)

    def prepare_backend_type(self, ffi):
        return (ffi._get_cached_btype(PointerType(self.item)),)

    def new_backend_type(self, ffi, BPtrItem):
        return ffi._backend.new_array_type(BPtrItem, self.length)

class StructOrUnion(BaseType):
    _attrs_ = ('name',)
        
    def __init__(self, name, fldnames, fldtypes, fldbitsize):
        self.name = name
        self.fldnames = fldnames
        self.fldtypes = fldtypes
        self.fldbitsize = fldbitsize

    def get_c_name(self, replace_with=''):
        return '%s %s%s' % (self.kind, self.name, replace_with)

    def prepare_backend_type(self, ffi):
        BType = self.get_btype(ffi)
        ffi._cached_btypes[self] = BType
        args = [BType]
        for tp in self.fldtypes:
            args.append(ffi._get_cached_btype(tp))
        return args

    def finish_backend_type(self, ffi, BType, *fldtypes):
        lst = zip(self.fldnames, fldtypes, self.fldbitsize)
        ffi._backend.complete_struct_or_union(BType, lst, self)
        return BType

class StructType(StructOrUnion):
    kind = 'struct'
    partial = False

    def check_not_partial(self):
        if self.partial:
            from . import ffiplatform
            raise ffiplatform.VerificationMissing(self.get_c_name())

    def get_btype(self, ffi):
        self.check_not_partial()
        return ffi._backend.new_struct_type(self.name)

    def verifier_declare_struct(self, verifier, name):
        if self.fldnames is None:
            assert not self.partial
            return
        verifier.write('{')
        verifier.write('struct __aligncheck__ { char x; struct %s y; };' %
                       self.name)
        verifier.write('struct %s __test__;' % self.name)
        verifier.write_printf('BEGIN struct %s' % self.name)
        verifier.write_printf('SIZE %ld %ld',
                              '(long)sizeof(struct %s)' % self.name,
                              '(long)offsetof(struct __aligncheck__, y)')
        for fname, ftype, fbitsize in zip(self.fldnames, self.fldtypes,
                                          self.fldbitsize):
            if fbitsize < 0:
                verifier.write_printf('FIELD ' + fname + ' %ld %ld',
                                      '(long)offsetof(struct %s, %s)' %
                                      (self.name, fname),
                                      '(long)sizeof(__test__.%s)' % fname)
            else:
                assert 0, "XXX: bitfield"
        verifier.write_printf('END')
        verifier.write('}')

class UnionType(StructOrUnion):
    kind = 'union'

    def get_btype(self, ffi):
        return ffi._backend.new_union_type(self.name)
    
class EnumType(BaseType):
    _attrs_ = ('name',)

    def __init__(self, name, enumerators, enumvalues):
        self.name = name
        self.enumerators = enumerators
        self.enumvalues = enumvalues

    def get_c_name(self, replace_with=''):
        return 'enum %s%s' % (self.name, replace_with)

    def new_backend_type(self, ffi):
        return ffi._backend.new_enum_type(self.name, self.enumerators,
                                          self.enumvalues)
