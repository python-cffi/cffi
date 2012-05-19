import pycparser    # http://code.google.com/p/pycparser/


class FFIError(Exception):
    pass


class FFI(object):
    
    def __init__(self, backend=None):
        if backend is None:
            from . import backend_ctypes
            backend = backend_ctypes.CTypesBackend()
        self._backend = backend
        self._declarations = {}
        self._cached_btypes = {}
        self._cached_parsed_types = {}
        self.C = FFILibrary(self, self._backend.load_library())

    def _declare(self, name, node):
        if name in self._declarations:
            raise FFIError("multiple declarations of %s" % (name,))
        self._declarations[name] = node

    def cdef(self, csource):
        parser = pycparser.CParser()
        ast = parser.parse(csource)
        v = CVisitor(self)
        v.visit(ast)

    def load(self, name):
        assert isinstance(name, str)
        return FFILibrary(self, self._backend.load_library(name))

    def typeof(self, cdecl):
        typenode = self._parse_type(cdecl)
        return self._get_btype(typenode)

    def new(self, cdecl, init=None):
        BType = self.typeof(cdecl)
        return BType(init)

    def _parse_type(self, cdecl):
        try:
            return self._cached_parsed_types[cdecl]
        except KeyError:
            parser = pycparser.CParser()
            csource = 'void __dummy(%s);' % cdecl
            ast = parser.parse(csource)
            # XXX: insert some sanity check
            typenode = ast.ext[0].type.args.params[0].type
            self._cached_parsed_types[cdecl] = typenode
            return typenode

    def _get_btype(self, typenode):
        if isinstance(typenode, pycparser.c_ast.ArrayDecl):
            # array type
            if typenode.dim is None:
                length = None
            else:
                assert isinstance(typenode.dim, pycparser.c_ast.Constant), (
                    "non-constant array length")
                length = int(typenode.dim.value)
            BItem = self._get_btype(typenode.type)
            return self._backend.get_cached_btype('new_array_type',
                                                  BItem, length)
        #
        if isinstance(typenode, pycparser.c_ast.PtrDecl):
            BItem = self._get_btype(typenode.type)
            return self._backend.get_cached_btype("new_pointer_type", BItem)
        #
        if isinstance(typenode, pycparser.c_ast.TypeDecl):
            type = typenode.type
            if isinstance(type, pycparser.c_ast.IdentifierType):
                # assume a primitive type.  get it from .names, but reduce
                # synonyms to a single chosen combination
                names = list(type.names)
                if names == ['signed'] or names == ['unsigned']:
                    names.append('int')
                if names[0] == 'signed' and names != ['signed', 'char']:
                    names.pop(0)
                if (len(names) > 1 and names[-1] == 'int'
                        and names != ['unsigned', 'int']):
                    names.pop()
                ident = ' '.join(names)
                return self._backend.get_cached_btype(
                    'new_primitive_type', ident)
            #
            if isinstance(type, pycparser.c_ast.Struct):
                return self._get_struct_or_union_type('struct', type)
            #
            if isinstance(type, pycparser.c_ast.Union):
                return self._get_struct_or_union_type('union', type)
        #
        raise FFIError("bad or unsupported type declaration")

    def _get_struct_or_union_type(self, kind, type):
        key = '%s %s' % (kind, type.name)
        assert key in self._declarations, "XXX opaque structs or unions"
        fields = self._declarations[key].decls
        fnames = [decl.name for decl in fields]
        btypes = [self._get_btype(decl.type) for decl in fields]
        return self._backend.get_cached_btype(
            'new_%s_type' % kind, type.name, tuple(fnames), tuple(btypes))


class FFILibrary(object):

    def __init__(self, ffi, backendlib):
        # XXX hide these attributes better
        self._ffi = ffi
        self._backendlib = backendlib

    def __getattr__(self, name):
        key = 'function ' + name
        if key in self._ffi._declarations:
            node = self._ffi._declarations[key]
            name = node.type.declname
            args = [self._ffi._get_btype(argdeclnode.type)
                    for argdeclnode in node.args.params]
            result = self._ffi._get_btype(node.type)
            value = self._backendlib.load_function(name, args, result)
            setattr(self, name, value)
            return value
        raise AttributeError(name)


class CVisitor(pycparser.c_ast.NodeVisitor):

    def __init__(self, ffi):
        self.ffi = ffi

    def visit_FuncDecl(self, node):
        self.ffi._declare('function ' + node.name, node)

    def visit_Struct(self, node):
        if node.decls is not None:
            self.ffi._declare('struct ' + node.name, node)

    def visit_Union(self, node):
        if node.decls is not None:
            self.ffi._declare('union ' + node.name, node)
