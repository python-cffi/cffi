import pycparser    # http://code.google.com/p/pycparser/


class FFIError(Exception):
    pass

class CDefError(Exception):
    def __str__(self):
        try:
            line = 'line %d: ' % (self.args[1].coord.line,)
        except (AttributeError, TypeError, IndexError):
            line = ''
        return '%s%s' % (line, self.args[0])


class FFI(object):
    
    def __init__(self, backend=None):
        if backend is None:
            from . import backend_ctypes
            backend = backend_ctypes.CTypesBackend()
        self._backend = backend
        self._declarations = {}
        self._cached_btypes = {}
        self._cached_parsed_types = {}
        self.C = _make_ffi_library(self, self._backend.load_library())
        #
        lines = []
        for name, equiv in self._backend.nonstandard_integer_types().items():
            lines.append('typedef %s %s;' % (equiv, name))
        self.cdef('\n'.join(lines))

    def _declare(self, name, node):
        if name in self._declarations:
            raise FFIError("multiple declarations of %s" % (name,))
        self._declarations[name] = node

    def cdef(self, csource):
        parser = pycparser.CParser()
        ast = parser.parse(csource)

        for decl in ast.ext:
            if isinstance(decl, pycparser.c_ast.Decl):
                self._parse_decl(decl)
            elif isinstance(decl, pycparser.c_ast.Typedef):
                if not decl.name:
                    raise CDefError("typedef does not declare any name", decl)
                self._declare('typedef ' + decl.name, decl.type)
            else:
                raise CDefError("unrecognized construct", decl)

    def _parse_decl(self, decl):
        node = decl.type
        if isinstance(node, pycparser.c_ast.FuncDecl):
            assert decl.name == node.type.declname
            self._declare('function ' + decl.name, node)
        else:
            if isinstance(node, pycparser.c_ast.Struct):
                if node.decls is not None:
                    self._declare('struct ' + node.name, node)
            elif isinstance(node, pycparser.c_ast.Union):
                if node.decls is not None:
                    self._declare('union ' + node.name, node)
            elif isinstance(node, pycparser.c_ast.Enum):
                if node.values is not None:
                    self._declare('enum ' + node.name, node)
            elif not decl.name:
                raise CDefError("construct does not declare any variable",
                                decl)
            #
            if decl.name:
                self._declare('variable ' + decl.name, node)

    def load(self, name):
        assert isinstance(name, str)
        return _make_ffi_library(self, self._backend.load_library(name), name)

    def typeof(self, cdecl):
        typenode = self._parse_type(cdecl)
        return self._get_btype(typenode)

    def sizeof(self, cdecl):
        if isinstance(cdecl, (str, unicode)):
            BType = self.typeof(cdecl)
            return BType._get_size()
        else:
            return cdecl._get_size_of_instance()

    def new(self, cdecl, init=None):
        BType = self.typeof(cdecl)
        return BType(init)

    def cast(self, cdecl, source):
        BType = self.typeof(cdecl)
        return BType._cast_from(source)

    def _parse_type(self, cdecl):
        try:
            return self._cached_parsed_types[cdecl]
        except KeyError:
            parser = pycparser.CParser()
            # XXX: for more efficiency we would need to poke into the
            # internals of CParser...  the following registers the
            # typedefs, because their presence or absence influences the
            # parsing itself (but what they are typedef'ed to plays no role)
            csourcelines = []
            for name in sorted(self._declarations):
                if name.startswith('typedef '):
                    csourcelines.append('typedef int %s;' % (name[8:],))
            #
            csourcelines.append('void __dummy(%s);' % cdecl)
            ast = parser.parse('\n'.join(csourcelines))
            # XXX: insert some sanity check
            typenode = ast.ext[-1].type.args.params[0].type
            self._cached_parsed_types[cdecl] = typenode
            return typenode

    def _get_btype_pointer(self, type):
        BItem = self._get_btype(type)
        if isinstance(type, pycparser.c_ast.FuncDecl):
            return BItem      # "pointer-to-function" ~== "function"
        if ('const' in type.quals and
            BItem is self._backend.get_cached_btype("new_primitive_type",
                                                    "char")):
            return self._backend.get_cached_btype("new_constcharp_type")
        else:
            return self._backend.get_cached_btype("new_pointer_type", BItem)

    def _get_btype(self, typenode, convert_array_to_pointer=False):
        # first, dereference typedefs, if necessary several times
        while (isinstance(typenode, pycparser.c_ast.TypeDecl) and
               isinstance(typenode.type, pycparser.c_ast.IdentifierType) and
               len(typenode.type.names) == 1 and
               ('typedef ' + typenode.type.names[0]) in self._declarations):
            typenode = self._declarations['typedef ' + typenode.type.names[0]]
        #
        if isinstance(typenode, pycparser.c_ast.ArrayDecl):
            # array type
            if convert_array_to_pointer:
                return self._get_btype_pointer(typenode.type)
            if typenode.dim is None:
                length = None
            else:
                length = self._parse_constant(typenode.dim)
            BItem = self._get_btype(typenode.type)
            return self._backend.get_cached_btype('new_array_type',
                                                  BItem, length)
        #
        if isinstance(typenode, pycparser.c_ast.PtrDecl):
            # pointer type
            return self._get_btype_pointer(typenode.type)
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
                if ident == 'void':
                    return self._backend.get_cached_btype("new_void_type")
                return self._backend.get_cached_btype(
                    'new_primitive_type', ident)
            #
            if isinstance(type, pycparser.c_ast.Struct):
                # 'struct foobar'
                return self._get_struct_or_union_type('struct', type)
            #
            if isinstance(type, pycparser.c_ast.Union):
                # 'union foobar'
                return self._get_struct_or_union_type('union', type)
            #
            if isinstance(type, pycparser.c_ast.Enum):
                # 'enum foobar'
                return self._get_enum_type(type)
        #
        if isinstance(typenode, pycparser.c_ast.FuncDecl):
            # a function type
            params = list(typenode.args.params)
            ellipsis = (len(params) > 0 and
                        isinstance(params[-1], pycparser.c_ast.EllipsisParam))
            if ellipsis:
                params.pop()
            if (len(params) == 1 and
                isinstance(params[0].type, pycparser.c_ast.TypeDecl) and
                isinstance(params[0].type.type, pycparser.c_ast.IdentifierType)
                    and list(params[0].type.type.names) == ['void']):
                del params[0]
            args = [self._get_btype(argdeclnode.type,
                                    convert_array_to_pointer=True)
                    for argdeclnode in params]
            result = self._get_btype(typenode.type)
            return self._backend.get_cached_btype(
                'new_function_type', tuple(args), result, ellipsis)
        #
        raise FFIError("bad or unsupported type declaration")

    def _get_struct_or_union_type(self, kind, type):
        name = type.name
        decls = type.decls
        if decls is None and name is not None:
            key = '%s %s' % (kind, name)
            if key in self._declarations:
                decls = self._declarations[key].decls
        if decls is not None:
            fnames = tuple([decl.name for decl in decls])
            btypes = tuple([self._get_btype(decl.type) for decl in decls])
        else:   # opaque struct or union
            fnames = None
            btypes = None
        return self._backend.get_cached_btype(
            'new_%s_type' % kind, name, fnames, btypes)

    def _get_enum_type(self, type):
        name = type.name
        decls = type.values
        if decls is None and name is not None:
            key = 'enum %s' % (name,)
            if key in self._declarations:
                decls = self._declarations[key].values
        if decls is not None:
            enumerators = tuple([enum.name for enum in decls.enumerators])
            enumvalues = []
            nextenumvalue = 0
            for enum in decls.enumerators:
                if enum.value is not None:
                    nextenumvalue = self._parse_constant(enum.value)
                enumvalues.append(nextenumvalue)
                nextenumvalue += 1
            enumvalues = tuple(enumvalues)
        else:   # opaque enum
            enumerators = None
            enumvalues = None
        return self._backend.get_cached_btype(
            'new_enum_type', name, enumerators, enumvalues)

    def _parse_constant(self, exprnode):
        # for now, limited to expressions that are an immediate number
        # or negative number
        if isinstance(exprnode, pycparser.c_ast.Constant):
            return int(exprnode.value)
        #
        if (isinstance(exprnode, pycparser.c_ast.UnaryOp) and
                exprnode.op == '-'):
            return -self._parse_constant(exprnode.expr)
        #
        raise FFIError("unsupported non-constant or "
                       "not immediately constant expression")


def _make_ffi_library(ffi, backendlib, libname=None):
    function_cache = {}
    backend = ffi._backend
    #
    class FFILibrary(object):
        def __getattribute__(self, name):
            if libname is None and name == 'errno':
                return backend.get_errno()
            #
            try:
                return function_cache[name]
            except KeyError:
                pass
            #
            key = 'function ' + name
            if key in ffi._declarations:
                node = ffi._declarations[key]
                assert name == node.type.declname
                BType = ffi._get_btype(node)
                value = backendlib.load_function(BType, name)
                function_cache[name] = value
                return value
            #
            key = 'variable ' + name
            if key in ffi._declarations:
                node = ffi._declarations[key]
                BType = ffi._get_btype(node)
                return backendlib.read_variable(BType, name)
            #
            raise AttributeError(name)

        def __setattr__(self, name, value):
            if libname is None and name == 'errno':
                backend.set_errno(value)
                return
            #
            key = 'variable ' + name
            if key in ffi._declarations:
                node = ffi._declarations[key]
                BType = ffi._get_btype(node)
                backendlib.write_variable(BType, name, value)
                return
            #
            raise AttributeError(name)
    #
    if libname is not None:
        FFILibrary.__name__ = 'FFILibrary_%s' % libname
    return FFILibrary()
