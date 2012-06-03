
class BaseType(object):
    is_struct_or_union_type = False
    
    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.__dict__ == other.__dict__)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        items = tuple([(name, getattr(self, name)) for name in self._attrs_])
        return hash((self.__class__, tuple(items)))

    def prepare_backend_type(self, ffi):
        pass

    def finish_backend_type(self, ffi, *args):
        try:
            return ffi._cached_btypes[self]
        except KeyError:
            return self.new_backend_type(ffi, *args)

    def get_backend_type(self, ffi):
        return ffi._get_cached_btype(self)

class VoidType(BaseType):
    _attrs_ = ()
    
    def new_backend_type(self, ffi):
        return ffi._backend.new_void_type()

    def __repr__(self):
        return '<void>'

void_type = VoidType()

class PrimitiveType(BaseType):
    _attrs_ = ('name',)

    def __init__(self, name):
        self.name = name

    def new_backend_type(self, ffi):
        return ffi._backend.new_primitive_type(self.name)

    def __repr__(self):
        return '<%s>' % (self.name,)

class FunctionType(BaseType):
    _attrs_ = ('args', 'result', 'ellipsis')

    def __init__(self, args, result, ellipsis):
        self.args = args
        self.result = result
        self.ellipsis = ellipsis

    def __repr__(self):
        args = ', '.join([repr(x) for x in self.args])
        if self.ellipsis:
            return '<(%s, ...) -> %r>' % (args, self.result)
        return '<(%s) -> %r>' % (args, self.result)

    def prepare_backend_type(self, ffi):
        args = [ffi._get_cached_btype(self.result)]
        for tp in self.args:
            args.append(ffi._get_cached_btype(tp))
        return args

    def new_backend_type(self, ffi, result, *args):
        return ffi._backend.new_function_type(args, result, self.ellipsis)

class PointerType(BaseType):
    _attrs_ = ('totype',)
    
    def __init__(self, totype):
        self.totype = totype

    def prepare_backend_type(self, ffi):
        return (ffi._get_cached_btype(self.totype),)

    def new_backend_type(self, ffi, BItem):
        return ffi._backend.new_pointer_type(BItem)

    def __repr__(self):
        return '<*%r>' % (self.totype,)

class ArrayType(BaseType):
    _attrs_ = ('item', 'length')

    def __init__(self, item, length):
        self.item = PointerType(item) # XXX why is this pointer?
        self.length = length

    def __repr__(self):
        if self.length is None:
            return '<%r[]>' % (self.item,)
        return '<%r[%s]>' % (self.item, self.length)

    def prepare_backend_type(self, ffi):
        return (ffi._get_cached_btype(self.item),)

    def new_backend_type(self, ffi, BItem):
        return ffi._backend.new_array_type(BItem, self.length)

class StructOrUnion(BaseType):
    _attrs_ = ('name',)
        
    is_struct_or_union_type = True
    
    def __init__(self, name, fldnames, fldtypes, fldbitsize):
        self.name = name
        self.fldnames = fldnames
        self.fldtypes = fldtypes
        self.fldbitsize = fldbitsize

    def __repr__(self):
        if self.fldnames is None:
            return '<struct %s>' % (self.name,)
        fldrepr = ', '.join(['%s: %r' % (name, tp) for name, tp in
                             zip(self.fldnames, self.fldtypes)])
        return '<struct %s {%s}>' % (self.name, fldrepr)

    def prepare_backend_type(self, ffi):
        BType = self.get_btype(ffi)
        ffi._cached_btypes[self] = BType
        args = [BType]
        for tp in self.fldtypes:
            args.append(ffi._get_cached_btype(tp))
        return args

    def finish_backend_type(self, ffi, BType, *fldtypes):
        ffi._backend.complete_struct_or_union(BType, self, fldtypes)
        return BType

class StructType(StructOrUnion):
    def get_btype(self, ffi):
        return ffi._backend.new_struct_type(self.name)

class UnionType(StructOrUnion):
    def get_btype(self, ffi):
        return ffi._backend.new_union_type(self.name)
    
