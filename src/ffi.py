import pycparser    # http://code.google.com/p/pycparser/


class FFIError(Exception):
    pass


class FFI(object):
    
    def __init__(self, backend):
        self._backend = backend
        self._functions = {}
        self._primitive_types = {}

    def cdef(self, csource):
        parser = pycparser.CParser()
        ast = parser.parse(csource)
        v = CVisitor(self)
        v.visit(ast)

    def load(self, name):
        return FFILibrary(self, self._backend.load_library(name))

    def _get_type(self, typenode):
        # assume a primitive type
        ident = ' '.join(typenode.type.names)
        if ident not in self._primitive_types:
            btype = self._backend.new_primitive_type(ident)
            self._primitive_types[ident] = btype
        return self._primitive_types[ident]


class FFILibrary(object):

    def __init__(self, ffi, backendlib):
        # XXX hide these attributes better
        self._ffi = ffi
        self._backendlib = backendlib

    def __getattr__(self, name):
        if name in self._ffi._functions:
            node = self._ffi._functions[name]
            name = node.type.declname
            args = [self._ffi._get_type(argdeclnode.type)
                    for argdeclnode in node.args.params]
            result = self._ffi._get_type(node.type)
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
