import sys, os, binascii, imp, shutil
from . import model, ffiplatform


class VGenericEngine(object):
    _class_key = 'g'
    _gen_python_module = False

    def __init__(self, verifier):
        self.verifier = verifier
        self.ffi = verifier.ffi
        self.export_symbols = []

    def patch_extension_kwds(self, kwds):
        # add 'export_symbols' to the dictionary.  Note that we add the
        # list before filling it.  When we fill it, it will thus also show
        # up in kwds['export_symbols'].
        kwds.setdefault('export_symbols', self.export_symbols)

    def collect_types(self):
        pass      # not needed in the generic engine

    def _prnt(self, what=''):
        self._f.write(what + '\n')

    def write_source_to_f(self):
        prnt = self._prnt
        # first paste some standard set of lines that are mostly '#include'
        prnt(cffimod_header)
        # then paste the C source given by the user, verbatim.
        prnt(self.verifier.preamble)
        #
        # call generate_gen_xxx_decl(), for every xxx found from
        # ffi._parser._declarations.  This generates all the functions.
        self._generate('decl')
        #
        # on Windows, distutils insists on putting init_cffi_xyz in
        # 'export_symbols', so instead of fighting it, just give up and
        # give it one
        if sys.platform == 'win32':
            prnt("void init%s(void) { }\n" % self.verifier.get_module_name())

    def load_library(self):
        # import it with the CFFI backend
        backend = self.ffi._backend
        module = backend.load_library(self.verifier.modulefilename)
        #
        # call loading_gen_struct() to get the struct layout inferred by
        # the C compiler
        self._load(module, 'loading')
        #
        # build the FFILibrary class and instance
        class FFILibrary(object):
            _cffi_generic_module = module
        library = FFILibrary()
        #
        # finally, call the loaded_gen_xxx() functions.  This will set
        # up the 'library' object.
        self._load(module, 'loaded', library=library)
        return library

    def _generate(self, step_name):
        for name, tp in self.ffi._parser._declarations.items():
            kind, realname = name.split(' ', 1)
            try:
                method = getattr(self, '_generate_gen_%s_%s' % (kind,
                                                                step_name))
            except AttributeError:
                raise ffiplatform.VerificationError(
                    "not implemented in verify(): %r" % name)
            method(tp, realname)

    def _load(self, module, step_name, **kwds):
        for name, tp in self.ffi._parser._declarations.items():
            kind, realname = name.split(' ', 1)
            method = getattr(self, '_%s_gen_%s' % (step_name, kind))
            method(tp, realname, module, **kwds)

    def _generate_nothing(self, tp, name):
        pass

    def _loaded_noop(self, tp, name, module, **kwds):
        pass

    # ----------
    # typedefs: generates no code so far

    _generate_gen_typedef_decl   = _generate_nothing
    _loading_gen_typedef         = _loaded_noop
    _loaded_gen_typedef          = _loaded_noop

    # ----------
    # function declarations

    def _generate_gen_function_decl(self, tp, name):
        assert isinstance(tp, model.FunctionPtrType)
        if tp.ellipsis:
            # cannot support vararg functions better than this: check for its
            # exact type (including the fixed arguments), and build it as a
            # constant function pointer (no _cffi_f_%s wrapper)
            self._generate_gen_const(False, name, tp)
            return
        prnt = self._prnt
        numargs = len(tp.args)
        argnames = []
        for i, type in enumerate(tp.args):
            indirection = ''
            if isinstance(type, model.StructOrUnion):
                indirection = '*'
            argnames.append('%sx%d' % (indirection, i))
        arglist = [type.get_c_name(' %s' % arg)
                   for type, arg in zip(tp.args, argnames)]
        arglist = ', '.join(arglist) or 'void'
        wrappername = '_cffi_f_%s' % name
        self.export_symbols.append(wrappername)
        funcdecl = ' %s(%s)' % (wrappername, arglist)
        prnt(tp.result.get_c_name(funcdecl))
        prnt('{')
        #
        if not isinstance(tp.result, model.VoidType):
            result_code = 'return '
        else:
            result_code = ''
        prnt('  %s%s(%s);' % (result_code, name, ', '.join(argnames)))
        prnt('}')
        prnt()

    _loading_gen_function = _loaded_noop

    def _loaded_gen_function(self, tp, name, module, library):
        assert isinstance(tp, model.FunctionPtrType)
        if tp.ellipsis:
            newfunction = self._load_constant(False, tp, name, module)
        else:
            indirections = []
            if any(isinstance(type, model.StructOrUnion) for type in tp.args):
                indirect_args = []
                for i, type in enumerate(tp.args):
                    if isinstance(type, model.StructOrUnion):
                        type = model.PointerType(type)
                        indirections.append((i, type))
                    indirect_args.append(type)
                tp = model.FunctionPtrType(tuple(indirect_args),
                                           tp.result, tp.ellipsis)
            BFunc = self.ffi._get_cached_btype(tp)
            wrappername = '_cffi_f_%s' % name
            newfunction = module.load_function(BFunc, wrappername)
            for i, type in indirections:
                newfunction = self._make_struct_wrapper(newfunction, i, type)
        setattr(library, name, newfunction)

    def _make_struct_wrapper(self, oldfunc, i, tp):
        backend = self.ffi._backend
        BType = self.ffi._get_cached_btype(tp)
        def newfunc(*args):
            args = args[:i] + (backend.newp(BType, args[i]),) + args[i+1:]
            return oldfunc(*args)
        return newfunc

    # ----------
    # named structs

    def _generate_gen_struct_decl(self, tp, name):
        assert name == tp.name
        self._generate_struct_or_union_decl(tp, 'struct', name)

    def _loading_gen_struct(self, tp, name, module):
        self._loading_struct_or_union(tp, 'struct', name, module)

    def _loaded_gen_struct(self, tp, name, module, **kwds):
        self._loaded_struct_or_union(tp)

    def _generate_struct_or_union_decl(self, tp, prefix, name):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        checkfuncname = '_cffi_check_%s_%s' % (prefix, name)
        layoutfuncname = '_cffi_layout_%s_%s' % (prefix, name)
        cname = ('%s %s' % (prefix, name)).strip()
        #
        prnt = self._prnt
        prnt('static void %s(%s *p)' % (checkfuncname, cname))
        prnt('{')
        prnt('  /* only to generate compile-time warnings or errors */')
        for i in range(len(tp.fldnames)):
            fname = tp.fldnames[i]
            ftype = tp.fldtypes[i]
            if (isinstance(ftype, model.PrimitiveType)
                and ftype.is_integer_type()):
                # accept all integers, but complain on float or double
                prnt('  (void)((p->%s) << 1);' % fname)
            else:
                # only accept exactly the type declared.  Note the parentheses
                # around the '*tmp' below.  In most cases they are not needed
                # but don't hurt --- except test_struct_array_field.
                prnt('  { %s = &p->%s; (void)tmp; }' % (
                    ftype.get_c_name('(*tmp)'), fname))
        prnt('}')
        self.export_symbols.append(layoutfuncname)
        prnt('ssize_t %s(ssize_t i)' % (layoutfuncname,))
        prnt('{')
        prnt('  struct _cffi_aligncheck { char x; %s y; };' % cname)
        if tp.partial:
            prnt('  static ssize_t nums[] = {')
            prnt('    1, sizeof(%s),' % cname)
            prnt('    offsetof(struct _cffi_aligncheck, y),')
            for fname in tp.fldnames:
                prnt('    offsetof(%s, %s),' % (cname, fname))
                prnt('    sizeof(((%s *)0)->%s),' % (cname, fname))
            prnt('    -1')
            prnt('  };')
            prnt('  return nums[i];')
        else:
            ffi = self.ffi
            BStruct = ffi._get_cached_btype(tp)
            conditions = [
                'sizeof(%s) != %d' % (cname, ffi.sizeof(BStruct)),
                'offsetof(struct _cffi_aligncheck, y) != %d' % (
                    ffi.alignof(BStruct),)]
            for fname, ftype in zip(tp.fldnames, tp.fldtypes):
                BField = ffi._get_cached_btype(ftype)
                conditions += [
                    'offsetof(%s, %s) != %d' % (
                        cname, fname, ffi.offsetof(BStruct, fname)),
                    'sizeof(((%s *)0)->%s) != %d' % (
                        cname, fname, ffi.sizeof(BField))]
            prnt('  if (%s ||' % conditions[0])
            for i in range(1, len(conditions)-1):
                prnt('      %s ||' % conditions[i])
            prnt('      %s) {' % conditions[-1])
            prnt('    return -1;')
            prnt('  }')
            prnt('  else {')
            prnt('    return 0;')
            prnt('  }')
        prnt('  /* the next line is not executed, but compiled */')
        prnt('  %s(0);' % (checkfuncname,))
        prnt('}')
        prnt()

    def _loading_struct_or_union(self, tp, prefix, name, module):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        layoutfuncname = '_cffi_layout_%s_%s' % (prefix, name)
        cname = ('%s %s' % (prefix, name)).strip()
        #
        BFunc = self.ffi.typeof("ssize_t(*)(ssize_t)")
        function = module.load_function(BFunc, layoutfuncname)
        layout = function(0)
        if layout < 0:
            raise ffiplatform.VerificationError(
                "incompatible layout for %s" % cname)
        elif layout == 0:
            assert not tp.partial
        else:
            totalsize = function(1)
            totalalignment = function(2)
            fieldofs = []
            fieldsize = []
            num = 3
            while True:
                x = function(num)
                if x < 0: break
                fieldofs.append(x)
                fieldsize.append(function(num+1))
                num += 2
            assert len(fieldofs) == len(fieldsize) == len(tp.fldnames)
            tp.fixedlayout = fieldofs, fieldsize, totalsize, totalalignment

    def _loaded_struct_or_union(self, tp):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        self.ffi._get_cached_btype(tp)   # force 'fixedlayout' to be considered

    # ----------
    # 'anonymous' declarations.  These are produced for anonymous structs
    # or unions; the 'name' is obtained by a typedef.

    def _generate_gen_anonymous_decl(self, tp, name):
        self._generate_struct_or_union_decl(tp, '', name)

    def _loading_gen_anonymous(self, tp, name, module):
        self._loading_struct_or_union(tp, '', name, module)

    def _loaded_gen_anonymous(self, tp, name, module, **kwds):
        self._loaded_struct_or_union(tp)

    # ----------
    # constants, likely declared with '#define'

    def _generate_gen_const(self, is_int, name, tp=None, category='const'):
        prnt = self._prnt
        funcname = '_cffi_%s_%s' % (category, name)
        self.export_symbols.append(funcname)
        if is_int:
            assert category == 'const'
            prnt('int %s(long long *out_value)' % funcname)
            prnt('{')
            prnt('  *out_value = (long long)(%s);' % (name,))
            prnt('  return (%s) <= 0;' % (name,))
            prnt('}')
        else:
            assert tp is not None
            prnt(tp.get_c_name(' %s(void)' % funcname),)
            prnt('{')
            if category == 'var':
                ampersand = '&'
            else:
                ampersand = ''
            prnt('  return (%s%s);' % (ampersand, name))
            prnt('}')
        prnt()

    def _generate_gen_constant_decl(self, tp, name):
        is_int = isinstance(tp, model.PrimitiveType) and tp.is_integer_type()
        self._generate_gen_const(is_int, name, tp)

    _loading_gen_constant = _loaded_noop

    def _load_constant(self, is_int, tp, name, module):
        funcname = '_cffi_const_%s' % name
        if is_int:
            BFunc = self.ffi.typeof("int(*)(long long*)")
            function = module.load_function(BFunc, funcname)
            p = self.ffi.new("long long*")
            negative = function(p)
            value = int(p[0])
            if value < 0 and not negative:
                value += (1 << (8*self.ffi.sizeof("long long")))
        else:
            BFunc = self.ffi.typeof(tp.get_c_name('(*)(void)'))
            function = module.load_function(BFunc, funcname)
            value = function()
        return value

    def _loaded_gen_constant(self, tp, name, module, library):
        is_int = isinstance(tp, model.PrimitiveType) and tp.is_integer_type()
        value = self._load_constant(is_int, tp, name, module)
        setattr(library, name, value)

    # ----------
    # enums

    def _generate_gen_enum_decl(self, tp, name):
        if tp.partial:
            for enumerator in tp.enumerators:
                self._generate_gen_const(True, enumerator)
            return
        #
        funcname = '_cffi_enum_%s' % name
        self.export_symbols.append(funcname)
        prnt = self._prnt
        prnt('int %s(char *out_error)' % funcname)
        prnt('{')
        for enumerator, enumvalue in zip(tp.enumerators, tp.enumvalues):
            prnt('  if (%s != %d) {' % (enumerator, enumvalue))
            prnt('    snprintf(out_error, 255, "in enum %s: '
                             '%s has the real value %d, not %d",')
            prnt('            "%s", "%s", (int)%s, %d);' % (
                name, enumerator, enumerator, enumvalue))
            prnt('    return -1;')
            prnt('  }')
        prnt('  return 0;')
        prnt('}')
        prnt()

    _loading_gen_enum = _loaded_noop

    def _loading_gen_enum(self, tp, name, module):
        if tp.partial:
            enumvalues = [self._load_constant(True, tp, enumerator, module)
                          for enumerator in tp.enumerators]
            tp.enumvalues = tuple(enumvalues)
            tp.partial = False
        else:
            BFunc = self.ffi.typeof("int(*)(char*)")
            funcname = '_cffi_enum_%s' % name
            function = module.load_function(BFunc, funcname)
            p = self.ffi.new("char[]", 256)
            if function(p) < 0:
                error = self.ffi.string(p)
                if sys.version_info >= (3,):
                    error = str(error, 'utf-8')
                raise ffiplatform.VerificationError(error)

    def _loaded_gen_enum(self, tp, name, module, library):
        for enumerator, enumvalue in zip(tp.enumerators, tp.enumvalues):
            setattr(library, enumerator, enumvalue)

    # ----------
    # macros: for now only for integers

    def _generate_gen_macro_decl(self, tp, name):
        assert tp == '...'
        self._generate_gen_const(True, name)

    _loading_gen_macro = _loaded_noop

    def _loaded_gen_macro(self, tp, name, module, library):
        value = self._load_constant(True, tp, name, module)
        setattr(library, name, value)

    # ----------
    # global variables

    def _generate_gen_variable_decl(self, tp, name):
        if isinstance(tp, model.ArrayType):
            tp_ptr = model.PointerType(tp.item)
            self._generate_gen_const(False, name, tp_ptr)
        else:
            tp_ptr = model.PointerType(tp)
            self._generate_gen_const(False, name, tp_ptr, category='var')

    _loading_gen_variable = _loaded_noop

    def _loaded_gen_variable(self, tp, name, module, library):
        if isinstance(tp, model.ArrayType):   # int a[5] is "constant" in the
                                              # sense that "a=..." is forbidden
            tp_ptr = model.PointerType(tp.item)
            value = self._load_constant(False, tp_ptr, name, module)
            # 'value' is a <cdata 'type *'> which we have to replace with
            # a <cdata 'type[N]'> if the N is actually known
            if tp.length is not None:
                BArray = self.ffi._get_cached_btype(tp)
                value = self.ffi.cast(BArray, value)
            setattr(library, name, value)
            return
        # remove ptr=<cdata 'int *'> from the library instance, and replace
        # it by a property on the class, which reads/writes into ptr[0].
        funcname = '_cffi_var_%s' % name
        BFunc = self.ffi.typeof(tp.get_c_name('*(*)(void)'))
        function = module.load_function(BFunc, funcname)
        ptr = function()
        def getter(library):
            return ptr[0]
        def setter(library, value):
            ptr[0] = value
        setattr(library.__class__, name, property(getter, setter))

cffimod_header = r'''
#include <stdio.h>
#include <stddef.h>
#include <stdarg.h>
#include <errno.h>
#include <sys/types.h>   /* XXX for ssize_t on some platforms */

#ifdef _WIN32
#  include <Windows.h>
#  define snprintf _snprintf
typedef __int8 int8_t;
typedef __int16 int16_t;
typedef __int32 int32_t;
typedef __int64 int64_t;
typedef unsigned __int8 uint8_t;
typedef unsigned __int16 uint16_t;
typedef unsigned __int32 uint32_t;
typedef unsigned __int64 uint64_t;
typedef SSIZE_T ssize_t;
#else
#  include <stdint.h>
#endif
'''
