import new
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
    r'''
    The main top-level class that you instantiate once, or once per module.

    Example usage:

        ffi = FFI()
        ffi.cdef("""
            int printf(const char *, ...);
        """)
        ffi.C.printf("hello, %s!\n", ffi.new("char[]", "world"))
    '''

    def __init__(self, backend=None):
        """Create an FFI instance.  The 'backend' argument is used to
        select a non-default backend, mostly for tests.
        """
        if backend is None:
            from . import backend_ctypes
            backend = backend_ctypes.CTypesBackend()
        self._backend = backend
        self._declarations = {}
        self._cached_btypes = {}
        self._parsed_types = new.module('parsed_types').__dict__
        self._new_types = new.module('new_types').__dict__
        self.C = _make_ffi_library(self, None)
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
        """Parse the given C source.  This registers all declared functions,
        types, and global variables.  The functions and global variables can
        then be accessed via 'ffi.C' or 'ffi.load()'.  The types can be used
        in 'ffi.new()' and other functions.
        """
        ast = _get_parser().parse(csource)

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
        """Load and return a dynamic library identified by 'name'.
        The standard C library is preloaded into 'ffi.C'.
        Note that functions and types declared by 'ffi.cdef()' are not
        linked to a particular library, just like C headers; in the
        library we only look for the actual (untyped) symbols.
        """
        assert isinstance(name, str)
        return _make_ffi_library(self, name)

    def typeof(self, cdecl):
        """Parse the C type given as a string and return the
        corresponding Python type: <class 'ffi.CData<...>'>.
        """
        try:
            return self._parsed_types[cdecl]
        except KeyError:
            typenode = self._parse_type(cdecl)
            btype = self._get_btype(typenode)
            self._parsed_types[cdecl] = btype
            return btype

    def sizeof(self, cdecl):
        """Return the size in bytes of the argument.  It can be a
        string naming a C type, or a 'cdata' instance.
        """
        if isinstance(cdecl, (str, unicode)):
            BType = self.typeof(cdecl)
            return self._backend.sizeof_type(BType)
        else:
            return self._backend.sizeof_instance(cdecl)

    def alignof(self, cdecl):
        """Return the natural alignment size in bytes of the C type
        given as a string.
        """
        BType = self.typeof(cdecl)
        return self._backend.alignof(BType)

    def offsetof(self, cdecl, fieldname):
        """Return the offset of the named field inside the given
        structure, which must be given as a C type name.
        """
        BType = self.typeof(cdecl)
        return self._backend.offsetof(BType, fieldname)

    def new(self, cdecl, init=None):
        """Allocate an instance 'x' of the named C type, and return a
        <cdata 'cdecl *'> object representing '&x'.  Such an object
        behaves like a pointer to the allocated memory.  When the
        <cdata> object goes out of scope, the memory is freed.

        The memory is initialized following the rules of declaring a
        global variable in C: by default it is zero-initialized, but
        an explicit initializer can be given which can be used to
        fill all or part of the memory.

        The returned <cdata> object has ownership of the value of
        type 'cdecl' that it points to.  This means that the raw data
        can be used as long as this object is kept alive, but must
        not be used for a longer time.  Be careful about that when
        copying the pointer to the memory somewhere else, e.g. into
        another structure.
        """
        try:
            BType = self._new_types[cdecl]
        except KeyError:
            typenode = self._parse_type(cdecl)
            BType = self._get_btype(typenode, force_pointer=True)
            self._new_types[cdecl] = BType
        #
        return BType(init)

    def cast(self, cdecl, source):
        """Similar to a C cast: returns an instance of the named C
        type initialized with the given 'source'.  The source is
        casted between integers or pointers of any type.
        """
        BType = self.typeof(cdecl)
        return self._backend.cast(BType, source)

    def string(self, pointer, length):
        """Return a Python string containing the data at the given
        raw pointer with the given size.  The pointer must be a
        <cdata 'void *'> or <cdata 'char *'>.
        """
        return self._backend.string(pointer, length)

    def callback(self, cdecl, python_callable):
        if not callable(python_callable):
            raise TypeError("the 'python_callable' argument is not callable")
        BFunc = self.typeof(cdecl)
        return BFunc(python_callable)

    def _parse_type(self, cdecl):
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
        ast = _get_parser().parse('\n'.join(csourcelines))
        # XXX: insert some sanity check
        typenode = ast.ext[-1].type.args.params[0].type
        return typenode

    def _get_cached_btype(self, methname, *args):
        try:
            BType = self._cached_btypes[methname, args]
        except KeyError:
            BType = getattr(self._backend, methname)(self, *args)
            self._cached_btypes[methname, args] = BType
        return BType

    def _get_btype_pointer(self, type):
        BItem = self._get_btype(type)
        if isinstance(type, pycparser.c_ast.FuncDecl):
            return BItem      # "pointer-to-function" ~== "function"
        return self._get_cached_btype("new_pointer_type", BItem)

    def _get_btype(self, typenode, convert_array_to_pointer=False,
                   force_pointer=False):
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
            return self._get_cached_btype('new_array_type', BItem, length)
        #
        if force_pointer:
            return self._get_btype_pointer(typenode)
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
                    return self._get_cached_btype("new_void_type")
                return self._get_cached_btype('new_primitive_type', ident)
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
            return self._get_cached_btype('new_function_type',
                                          tuple(args), result, ellipsis)
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
            bitfields = tuple(map(self._get_bitfield_size, decls))
        else:   # opaque struct or union
            fnames = None
            btypes = None
            bitfields = None
        return self._get_cached_btype('new_%s_type' % kind, name,
                                      fnames, btypes, bitfields)

    def _get_bitfield_size(self, decl):
        if decl.bitsize is None:
            return None
        else:
            return self._parse_constant(decl.bitsize)

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
        return self._get_cached_btype('new_enum_type', name,
                                      enumerators, enumvalues)

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

    def verify(self, preamble='', **kwargs):
        """ Verify that the current ffi signatures compile on this machine
        """
        from ffi.verifier import Verifier
        return Verifier().verify(self, preamble, **kwargs)

def _make_ffi_library(ffi, libname):
    name = libname
    if name is None:
        name = 'c'    # on Posix only
    if '/' in name:
        path = name
    else:
        import ctypes.util
        path = ctypes.util.find_library(name)
        if path is None:
            raise OSError("library not found: %r" % (name,))
    #
    backend = ffi._backend
    backendlib = backend.load_library(path)
    function_cache = {}
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


_parser_cache = None

def _get_parser():
    global _parser_cache
    if _parser_cache is None:
        _parser_cache = pycparser.CParser()
    return _parser_cache
