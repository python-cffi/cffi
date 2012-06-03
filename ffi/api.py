import new
import pycparser    # http://code.google.com/p/pycparser/
from ffi import ffiplatform, cparser, model

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
        self._parser = cparser.Parser()
        self._cached_btypes = {}
        self._parsed_types = new.module('parsed_types').__dict__
        self._new_types = new.module('new_types').__dict__
        if hasattr(backend, 'set_ffi'):
            backend.set_ffi(self)
        self.C = _make_ffi_library(self, None)
        #
        lines = []
        by_size = {}
        for cname in ['long long', 'long', 'int', 'short', 'char']:
            by_size[self.sizeof(cname)] = cname
        for name, size in self._backend.nonstandard_integer_types().items():
            if size & 0x1000:   # unsigned
                equiv = 'unsigned %s'
                size &= ~0x1000
            else:
                equiv = 'signed %s'
            lines.append('typedef %s %s;' % (equiv % by_size[size], name))
        self.cdef('\n'.join(lines))

    def _declare(self, name, node):
        xxx
        if name == 'typedef __dotdotdot__':
            return
        if name in self._declarations:
            raise FFIError("multiple declarations of %s" % (name,))
        self._declarations[name] = node

    def cdef(self, csource):
        """Parse the given C source.  This registers all declared functions,
        types, and global variables.  The functions and global variables can
        then be accessed via 'ffi.C' or 'ffi.load()'.  The types can be used
        in 'ffi.new()' and other functions.
        """
        self._parser.parse(csource)
        #for decl in ast.ext:
        #    if isinstance(decl, pycparser.c_ast.Decl):
        #        self._parse_decl(decl)
        #    elif isinstance(decl, pycparser.c_ast.Typedef):
        #        if not decl.name:
        #            raise CDefError("typedef does not declare any name", decl)
        #        self._declare('typedef ' + decl.name, decl.type)
        #    else:
        #        raise CDefError("unrecognized construct", decl)

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
        It can also be used on 'cdata' instance to get its C type.
        """
        if isinstance(cdecl, (str, unicode)):
            try:
                return self._parsed_types[cdecl]
            except KeyError:
                type = self._parser.parse_type(cdecl)
                btype = type.get_backend_type(self)
                self._parsed_types[cdecl] = btype
                return btype
        else:
            return self._backend.typeof_instance(cdecl)

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
            type = self._parser.parse_type(cdecl, force_pointer=True)
            BType = type.get_backend_type(self)
            self._new_types[cdecl] = BType
        #
        return self._backend.new(BType, init)

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
        return self._backend.callback(BFunc, python_callable)

    def _get_cached_btype(self, type):
        try:
            BType = self._cached_btypes[type]
        except KeyError:
            BType = type.new_backend_type(self)
            self._cached_btypes[type] = BType
            if type.is_struct_or_union_type:
                self._backend.complete_struct_or_union(BType, type)
        return BType

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
            enumerators = ()
            enumvalues = ()
        return self._get_cached_btype('new_enum_type', name,
                                      enumerators, enumvalues)

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
