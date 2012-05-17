import pycparser    # http://code.google.com/p/pycparser/


class FFIError(Exception):
    pass


class FFI(object):
    
    def __init__(self, backend=None):
        if backend is None:
            from . import backend_ctypes
            backend = backend_ctypes.CTypesBackend()
        self._backend = backend
        self._functions = {}
        self._cached_btypes = {}
        self._cached_parsed_types = {}
        self.C = FFILibrary(self, self._backend.load_library())

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

    def new(self, cdecl, *args):
        btype = self.typeof(cdecl)
        return btype(*args)

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
            assert isinstance(typenode.dim, pycparser.c_ast.Constant), (
                "non-constant array length")
            length = int(typenode.dim.value)
            bitem = self._get_btype(typenode.type)
            return self._get_cached_btype('new_array_type', bitem, length)
        else:
            # assume a primitive type
            ident = ' '.join(typenode.type.names)
            return self._get_cached_btype('new_primitive_type', ident)

    def _get_cached_btype(self, methname, *args):
        try:
            btype = self._cached_btypes[methname, args]
        except KeyError:
            btype = getattr(self._backend, methname)(*args)
            self._cached_btypes[methname, args] = btype
        return btype


class FFILibrary(object):

    def __init__(self, ffi, backendlib):
        # XXX hide these attributes better
        self._ffi = ffi
        self._backendlib = backendlib

    def __getattr__(self, name):
        if name in self._ffi._functions:
            node = self._ffi._functions[name]
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
        # assume for now primitive args and result types
        name = node.type.declname
        if name in self.ffi._functions:
            raise FFIError("multiple declaration of function %r" % (name,))
        self.ffi._functions[name] = node
