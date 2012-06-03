
class BaseType(object):
    is_struct_or_union_type = False
    
    def __eq__(self, other):
        return (self.__class__ == other.__class__ and
                self.__dict__ == other.__dict__)

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        items = self.__dict__.items()
        items.sort()
        return hash((self.__class__, tuple(items)))

    def get_backend_type(self, ffi):
        return ffi._get_cached_btype(self)

class VoidType(BaseType):
    def new_backend_type(self, ffi):
        return ffi._backend.new_void_type()

    def __repr__(self):
        return '<void>'

void_type = VoidType()

class PrimitiveType(BaseType):
    def __init__(self, name):
        self.name = name

    def new_backend_type(self, ffi):
        return ffi._backend.new_primitive_type(self.name)

    def __repr__(self):
        return '<%s>' % (self.name,)

class FunctionType(BaseType):
    pass

class PointerType(BaseType):
    def __init__(self, totype):
        self.totype = totype

    def new_backend_type(self, ffi):
        return ffi._backend.new_pointer_type(ffi._get_cached_btype(self.totype))

    def __repr__(self):
        return '<*%r>' % (self.totype,)

class ArrayType(BaseType):
    def __init__(self, item, length):
        self.item = PointerType(item) # XXX why is this pointer?
        self.length = length

    def __repr__(self):
        if self.length is None:
            return '<%r[]>' % (self.item,)
        return '<%r[%s]>' % (self.item, self.length)

    def new_backend_type(self, ffi):
        return ffi._backend.new_array_type(ffi._get_cached_btype(self.item),
                                           self.length)

class StructType(BaseType):
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

    def new_backend_type(self, ffi):
        return ffi._backend.new_struct_type(self.name)
