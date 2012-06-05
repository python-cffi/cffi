
from . import api, model
import pycparser

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
                self._parse_decl(decl)
            elif isinstance(decl, pycparser.c_ast.Typedef):
                if not decl.name:
                    raise api.CDefError("typedef does not declare any name",
                                        decl)
                if decl.name != '__dotdotdot__':
                    self._declare('typedef ' + decl.name,
                                  self._get_type(decl.type))
            else:
                raise api.CDefError("unrecognized construct", decl)

    def _parse_decl(self, decl):
        node = decl.type
        if isinstance(node, pycparser.c_ast.FuncDecl):
            self._declare('function ' + decl.name,
                          self._get_type(node, name=decl.name))
        else:
            if isinstance(node, pycparser.c_ast.Struct):
                # XXX do we need self._declare in any of those?
                if node.decls is not None:
                    self._get_struct_or_union_type('struct', node)
            elif isinstance(node, pycparser.c_ast.Union):
                if node.decls is not None:
                    self._get_struct_or_union_type('union', node)
            elif isinstance(node, pycparser.c_ast.Enum):
                if node.values is not None:
                    self._get_enum_type(node)
            elif not decl.name:
                raise api.CDefError("construct does not declare any variable",
                                    decl)
            #
            if decl.name:
                self._declare('variable ' + decl.name, self._get_type(node))

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

    def _declare(self, name, obj):
        if name in self._declarations:
            raise api.FFIError("multiple declarations of %s" % (name,))
        self._declarations[name] = obj

    def _get_type_pointer(self, type):
        if isinstance(type, model.FunctionType):
            return type # "pointer-to-function" ~== "function"
        return model.PointerType(type)

    def _get_type(self, typenode, convert_array_to_pointer=False,
                  force_pointer=False, name=None):
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
            # array type
            if convert_array_to_pointer:
                return self._get_type_pointer(self._get_type(typenode.type))
            if typenode.dim is None:
                length = None
            else:
                length = self._parse_constant(typenode.dim)
            return model.ArrayType(self._get_type(typenode.type), length)
        #
        if force_pointer:
            return model.PointerType(self._get_type(typenode))
        #
        if isinstance(typenode, pycparser.c_ast.PtrDecl):
            # pointer type
            return self._get_type_pointer(self._get_type(typenode.type))
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
            return self._parse_function_type(typenode, name)
        #
        raise api.FFIError("bad or unsupported type declaration")

    def _parse_function_type(self, typenode, name=None):
        params = list(getattr(typenode.args, 'params', []))
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
        args = [self._get_type(argdeclnode.type,
                               convert_array_to_pointer=True)
                for argdeclnode in params]
        result = self._get_type(typenode.type)
        return model.FunctionType(name, tuple(args), result, ellipsis)

    def _get_struct_or_union_type(self, kind, type):
        name = type.name
        key = '%s %s' % (kind, name)
        if key in self._declarations:
            return self._declarations[key]
        #
        decls = type.decls
        # create an empty type for now
        if kind == 'struct':
            tp = model.StructType(name, None, None, None)
        else:
            assert kind == 'union'
            tp = model.UnionType(name, None, None, None)
        self._declarations[key] = tp

        #if decls is None and name is not None:
        #    key = '%s %s' % (kind, name)
        #    if key in self._declarations:
        #        decls = self._declarations[key].decls
        if decls is None:
            return tp    # opaque type, so far
        #
        # mark it as complete *first*, to handle recursion
        fldnames = []
        fldtypes = []
        fldbitsize = []
        for decl in decls:
            if (isinstance(decl.type, pycparser.c_ast.IdentifierType) and
                    ''.join(decl.type.names) == '__dotdotdot__'):
                xxxx
                # XXX pycparser is inconsistent: 'names' should be a list
                # of strings, but is sometimes just one string.  Use
                # str.join() as a way to cope with both.
            if decl.bitsize is None:
                bitsize = -1
            else:
                bitsize = self._parse_constant(decl.bitsize)
            fldnames.append(decl.name)
            fldtypes.append(self._get_type(decl.type))
            fldbitsize.append(bitsize)
        tp.fldnames = tuple(fldnames)
        tp.fldtypes = tuple(fldtypes)
        tp.fldbitsize = tuple(fldbitsize)
        return tp

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
        raise api.FFIError("unsupported non-constant or "
                           "not immediately constant expression")

    def _get_enum_type(self, type):
        name = type.name
        decls = type.values
        key = 'enum %s' % (name,)
        if key in self._declarations:
            return self._declarations[key]
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
            tp = model.EnumType(name, enumerators, enumvalues)
            self._declarations[key] = tp
        else:   # opaque enum
            enumerators = ()
            enumvalues = ()
            tp = model.EnumType(name, (), ())
        return tp
