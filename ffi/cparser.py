
import ffi
import pycparser
from ffi import model

_parser_cache = None

def _get_parser():
    global _parser_cache
    if _parser_cache is None:
        _parser_cache = pycparser.CParser()
    return _parser_cache

class Parser(object):
    def __init__(self):
        self._declarations = {}

    def parse(self, csource):
        csource = ("typedef int __dotdotdot__;\n" +
                   csource.replace('...', '__dotdotdot__'))
        ast = _get_parser().parse(csource)
        for decl in ast.ext:
            if isinstance(decl, pycparser.c_ast.Decl):
                xxx
                self._parse_decl(decl)
            elif isinstance(decl, pycparser.c_ast.Typedef):
                if not decl.name:
                    raise ffi.CDefError("typedef does not declare any name",
                                        decl)
                self._declare('typedef ' + decl.name, decl.type)
            else:
                raise ffi.CDefError("unrecognized construct", decl)

    def parse_type(self, cdecl, force_pointer=False,
                   convert_array_to_pointer=False):
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
        typenode = ast.ext[-1].type.args.params[0].type
        return self._get_type(typenode, force_pointer=force_pointer,
                              convert_array_to_pointer=convert_array_to_pointer)

    def _declare(self, name, node):
        if name == 'typedef __dotdotdot__':
            return
        if name in self._declarations:
            raise ffi.FFIError("multiple declarations of %s" % (name,))
        self._declarations[name] = self._get_type(node)

    def _get_type_pointer(self, type):
        if isinstance(type, model.FunctionType):
            return type # "pointer-to-function" ~== "function"
        return model.PointerType(type)

    def _get_type(self, typenode, convert_array_to_pointer=False,
                  force_pointer=False):
        # first, dereference typedefs, if we have it already parsed, we're good
        if (isinstance(typenode, pycparser.c_ast.TypeDecl) and
            isinstance(typenode.type, pycparser.c_ast.IdentifierType) and
            len(typenode.type.names) == 1 and
            ('typedef ' + typenode.type.names[0]) in self._declarations):
            type = self._declarations['typedef ' + typenode.type.names[0]]
            if force_pointer:
                return self._get_type_pointer(type)
            if convert_array_to_pointer:
                xxx
            return type
        #
        if isinstance(typenode, pycparser.c_ast.ArrayDecl):
            xxx
            # array type
            if convert_array_to_pointer:
                return self._get_btype_pointer(typenode.type)
            if typenode.dim is None:
                length = None
            else:
                length = self._parse_constant(typenode.dim)
            BItem = self._get_btype(typenode.type)
            BPtr = self._get_cached_btype('new_pointer_type', BItem)
            return self._get_cached_btype('new_array_type', BPtr, length)
        #
        if force_pointer:
            return self._get_type_pointer(self._get_type(typenode))
        #
        if isinstance(typenode, pycparser.c_ast.PtrDecl):
            xxx
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
                    return model.void_type
                return model.PrimitiveType(ident)
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
            ellipsis = (
                len(params) > 0 and
                isinstance(params[-1].type, pycparser.c_ast.TypeDecl) and
                isinstance(params[-1].type.type,
                           pycparser.c_ast.IdentifierType) and
                ''.join(params[-1].type.type.names) == '__dotdotdot__')
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
        raise ffi.FFIError("bad or unsupported type declaration")
