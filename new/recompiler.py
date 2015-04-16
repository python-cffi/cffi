import os, sys
from cffi1 import ffiplatform, model
from cffi_opcode import *


class Recompiler:

    def __init__(self, ffi, module_name):
        self.ffi = ffi
        self.module_name = module_name

    def collect_type_table(self):
        self._typesdict = {}
        self._generate("collecttype")
        #
        all_decls = sorted(self._typesdict, key=str)
        #
        # prepare all FUNCTION bytecode sequences first
        self.cffi_types = []
        for tp in all_decls:
            if tp.is_raw_function:
                assert self._typesdict[tp] is None
                self._typesdict[tp] = len(self.cffi_types)
                self.cffi_types.append(tp)     # placeholder
                for tp1 in tp.args:
                    assert isinstance(tp1, (model.VoidType,
                                            model.PrimitiveType,
                                            model.PointerType,
                                            model.StructOrUnionOrEnum,
                                            model.FunctionPtrType))
                    if self._typesdict[tp1] is None:
                        self._typesdict[tp1] = len(self.cffi_types)
                    self.cffi_types.append(tp1)   # placeholder
                self.cffi_types.append('END')     # placeholder
        #
        # prepare all OTHER bytecode sequences
        for tp in all_decls:
            if not tp.is_raw_function and self._typesdict[tp] is None:
                self._typesdict[tp] = len(self.cffi_types)
                self.cffi_types.append(tp)        # placeholder
                if tp.is_array_type and tp.length is not None:
                    self.cffi_types.append('LEN') # placeholder
        assert None not in self._typesdict.values()
        #
        # emit all bytecode sequences now
        for tp in all_decls:
            method = getattr(self, '_emit_bytecode_' + tp.__class__.__name__)
            method(tp, self._typesdict[tp])
        #
        # consistency check
        for op in self.cffi_types:
            assert isinstance(op, CffiOp)

    def _do_collect_type(self, tp):
        if not isinstance(tp, model.BaseTypeByIdentity):
            if isinstance(tp, tuple):
                for x in tp:
                    self._do_collect_type(x)
            return
        if tp not in self._typesdict:
            self._typesdict[tp] = None
            if isinstance(tp, model.FunctionPtrType):
                self._do_collect_type(tp.as_raw_function())
            else:
                for _, x in tp._get_items():
                    self._do_collect_type(x)

    def _get_declarations(self):
        return sorted(self.ffi._parser._declarations.items())

    def _generate(self, step_name):
        for name, tp in self._get_declarations():
            kind, realname = name.split(' ', 1)
            try:
                method = getattr(self, '_generate_cpy_%s_%s' % (kind,
                                                                step_name))
            except AttributeError:
                raise ffiplatform.VerificationError(
                    "not implemented in verify(): %r" % name)
            try:
                method(tp, realname)
            except Exception as e:
                model.attach_exception_info(e, name)
                raise

    # ----------

    def _prnt(self, what=''):
        self._f.write(what + '\n')

    def write_source_to_f(self, f, preamble):
        self._f = f
        prnt = self._prnt
        #
        # first the '#include'
        prnt('#include "_cffi_include.h"')
        #
        # then paste the C source given by the user, verbatim.
        prnt('/************************************************************/')
        prnt()
        prnt(preamble)
        prnt()
        prnt('/************************************************************/')
        prnt()
        #
        # the declaration of '_cffi_types'
        prnt('static void *_cffi_types[] = {')
        for op in self.cffi_types:
            prnt('  %s,' % (op.as_c_expr(),))
        if not self.cffi_types:
            prnt('  0')
        prnt('};')
        prnt()
        #
        # call generate_cpy_xxx_decl(), for every xxx found from
        # ffi._parser._declarations.  This generates all the functions.
        self._generate("decl")
        #
        # the declaration of '_cffi_globals' and '_cffi_typenames'
        nums = {}
        self._lsts = {"global": [], "typename": []}
        self._generate("ctx")
        for step_name in ["global", "typename"]:
            lst = self._lsts[step_name]
            nums[step_name] = len(lst)
            if nums[step_name] > 0:
                lst.sort()  # sort by name, which is at the start of each line
                prnt('static const struct _cffi_%s_s _cffi_%ss[] = {' % (
                    step_name, step_name))
                for line in lst:
                    prnt(line)
                prnt('};')
                prnt()
        #
        # XXX
        nums['struct_union'] = 0
        nums['enum'] = 0
        #
        # the declaration of '_cffi_type_context'
        prnt('static const struct _cffi_type_context_s _cffi_type_context = {')
        prnt('  _cffi_types,')
        ALL_STEPS = ["global", "struct_union", "enum", "typename"]
        for step_name in ALL_STEPS:
            if nums[step_name] > 0:
                prnt('  _cffi_%ss,' % step_name)
                if step_name == 'struct_union':
                    prnt('  _cffi_fields,')
            else:
                prnt('  NULL,  /* no %ss */' % step_name)
                if step_name == 'struct_union':
                    prnt('  NULL,  /* no fields */')
        for step_name in ALL_STEPS:
            prnt('  %d,  /* num_%ss */' % (nums[step_name], step_name))
        prnt('};')
        prnt()
        #
        # the init function, loading _cffi1_backend and calling a method there
        prnt('PyMODINIT_FUNC')
        prnt('init%s(void)' % (self.module_name,))
        prnt('{')
        prnt('  if (_cffi_init() < 0)')
        prnt('    return;')
        prnt('  _cffi_init_module("%s", &_cffi_type_context);' % (
            self.module_name,))
        prnt('}')

    # ----------

    def _convert_funcarg_to_c(self, tp, fromvar, tovar, errcode):
        extraarg = ''
        if isinstance(tp, model.PrimitiveType):
            if tp.is_integer_type() and tp.name != '_Bool':
                converter = '_cffi_to_c_int'
                extraarg = ', %s' % tp.name
            else:
                converter = '(%s)_cffi_to_c_%s' % (tp.get_c_name(''),
                                                   tp.name.replace(' ', '_'))
            errvalue = '-1'
        #
        elif isinstance(tp, model.PointerType):
            self._convert_funcarg_to_c_ptr_or_array(tp, fromvar,
                                                    tovar, errcode)
            return
        #
        elif isinstance(tp, (model.StructOrUnion, model.EnumType)):
            # a struct (not a struct pointer) as a function argument
            self._prnt('  if (_cffi_to_c((char *)&%s, _cffi_type(%d), %s) < 0)'
                      % (tovar, self._gettypenum(tp), fromvar))
            self._prnt('    %s;' % errcode)
            return
        #
        elif isinstance(tp, model.FunctionPtrType):
            converter = '(%s)_cffi_to_c_pointer' % tp.get_c_name('')
            extraarg = ', _cffi_type(%d)' % self._gettypenum(tp)
            errvalue = 'NULL'
        #
        else:
            raise NotImplementedError(tp)
        #
        self._prnt('  %s = %s(%s%s);' % (tovar, converter, fromvar, extraarg))
        self._prnt('  if (%s == (%s)%s && PyErr_Occurred())' % (
            tovar, tp.get_c_name(''), errvalue))
        self._prnt('    %s;' % errcode)

    def _extra_local_variables(self, tp, localvars):
        if isinstance(tp, model.PointerType):
            localvars.add('Py_ssize_t datasize')

    def _convert_funcarg_to_c_ptr_or_array(self, tp, fromvar, tovar, errcode):
        self._prnt('  datasize = _cffi_prepare_pointer_call_argument(')
        self._prnt('      _cffi_type(%d), %s, (char **)&%s);' % (
            self._gettypenum(tp), fromvar, tovar))
        self._prnt('  if (datasize != 0) {')
        self._prnt('    if (datasize < 0)')
        self._prnt('      %s;' % errcode)
        self._prnt('    %s = alloca((size_t)datasize);' % (tovar,))
        self._prnt('    memset((void *)%s, 0, (size_t)datasize);' % (tovar,))
        self._prnt('    if (_cffi_convert_array_from_object('
                   '(char *)%s, _cffi_type(%d), %s) < 0)' % (
            tovar, self._gettypenum(tp), fromvar))
        self._prnt('      %s;' % errcode)
        self._prnt('  }')

    def _convert_expr_from_c(self, tp, var, context):
        if isinstance(tp, model.PrimitiveType):
            if tp.is_integer_type():
                return '_cffi_from_c_int(%s, %s)' % (var, tp.name)
            elif tp.name != 'long double':
                return '_cffi_from_c_%s(%s)' % (tp.name.replace(' ', '_'), var)
            else:
                return '_cffi_from_c_deref((char *)&%s, _cffi_type(%d))' % (
                    var, self._gettypenum(tp))
        elif isinstance(tp, (model.PointerType, model.FunctionPtrType)):
            return '_cffi_from_c_pointer((char *)%s, _cffi_type(%d))' % (
                var, self._gettypenum(tp))
        elif isinstance(tp, model.ArrayType):
            return '_cffi_from_c_pointer((char *)%s, _cffi_type(%d))' % (
                var, self._gettypenum(model.PointerType(tp.item)))
        elif isinstance(tp, model.StructType):
            if tp.fldnames is None:
                raise TypeError("'%s' is used as %s, but is opaque" % (
                    tp._get_c_name(), context))
            return '_cffi_from_c_struct((char *)&%s, _cffi_type(%d))' % (
                var, self._gettypenum(tp))
        elif isinstance(tp, model.EnumType):
            return '_cffi_from_c_deref((char *)&%s, _cffi_type(%d))' % (
                var, self._gettypenum(tp))
        else:
            raise NotImplementedError(tp)

    # ----------
    # typedefs

    def _generate_cpy_typedef_collecttype(self, tp, name):
        self._do_collect_type(tp)

    def _generate_cpy_typedef_decl(self, tp, name):
        pass

    def _generate_cpy_typedef_ctx(self, tp, name):
        type_index = self._typesdict[tp]
        self._lsts["typename"].append(
            '  { "%s", %d },' % (name, type_index))

    # ----------
    # function declarations

    def _generate_cpy_function_collecttype(self, tp, name):
        self._do_collect_type(tp.as_raw_function())

    def _generate_cpy_function_decl(self, tp, name):
        assert isinstance(tp, model.FunctionPtrType)
        if tp.ellipsis:
            # cannot support vararg functions better than this: check for its
            # exact type (including the fixed arguments), and build it as a
            # constant function pointer (no CPython wrapper)
            self._generate_cpy_const(False, name, tp)
            return
        prnt = self._prnt
        numargs = len(tp.args)
        if numargs == 0:
            argname = 'noarg'
        elif numargs == 1:
            argname = 'arg0'
        else:
            argname = 'args'
        prnt('static PyObject *')
        prnt('_cffi_f_%s(PyObject *self, PyObject *%s)' % (name, argname))
        prnt('{')
        #
        context = 'argument of %s' % name
        for i, type in enumerate(tp.args):
            prnt('  %s;' % type.get_c_name(' x%d' % i, context))
        #
        localvars = set()
        for type in tp.args:
            self._extra_local_variables(type, localvars)
        for decl in localvars:
            prnt('  %s;' % (decl,))
        #
        if not isinstance(tp.result, model.VoidType):
            result_code = 'result = '
            context = 'result of %s' % name
            prnt('  %s;' % tp.result.get_c_name(' result', context))
        else:
            result_code = ''
        #
        if len(tp.args) > 1:
            rng = range(len(tp.args))
            for i in rng:
                prnt('  PyObject *arg%d;' % i)
            prnt()
            prnt('  if (!PyArg_ParseTuple(args, "%s:%s", %s))' % (
                'O' * numargs, name, ', '.join(['&arg%d' % i for i in rng])))
            prnt('    return NULL;')
        prnt()
        #
        for i, type in enumerate(tp.args):
            self._convert_funcarg_to_c(type, 'arg%d' % i, 'x%d' % i,
                                       'return NULL')
            prnt()
        #
        prnt('  Py_BEGIN_ALLOW_THREADS')
        prnt('  _cffi_restore_errno();')
        prnt('  { %s%s(%s); }' % (
            result_code, name,
            ', '.join(['x%d' % i for i in range(len(tp.args))])))
        prnt('  _cffi_save_errno();')
        prnt('  Py_END_ALLOW_THREADS')
        prnt()
        #
        prnt('  (void)self; /* unused */')
        if numargs == 0:
            prnt('  (void)noarg; /* unused */')
        if result_code:
            prnt('  return %s;' %
                 self._convert_expr_from_c(tp.result, 'result', 'result type'))
        else:
            prnt('  Py_INCREF(Py_None);')
            prnt('  return Py_None;')
        prnt('}')
        prnt()

    def _generate_cpy_function_ctx(self, tp, name):
        if tp.ellipsis:
            XXX
        type_index = self._typesdict[tp.as_raw_function()]
        numargs = len(tp.args)
        if numargs == 0:
            meth_kind = 'N'   # 'METH_NOARGS'
        elif numargs == 1:
            meth_kind = 'O'   # 'METH_O'
        else:
            meth_kind = 'V'   # 'METH_VARARGS'
        self._lsts["global"].append(
            '  { "%s", _cffi_f_%s, _CFFI_OP(_CFFI_OP_CPYTHON_BLTN_%s, %d) },'
            % (name, name, meth_kind, type_index))

    # ----------
    # constants, declared with "static const ..."

    def _generate_cpy_const(self, is_int, name, tp=None, category='const',
                            check_value=None):
        assert check_value is None # XXX
        prnt = self._prnt
        funcname = '_cffi_%s_%s' % (category, name)
        if is_int:
            prnt('static int %s(unsigned long long *o)' % funcname)
            prnt('{')
            prnt('  *o = (unsigned long long)((%s) << 0);'
                 '  /* check that we get an integer */' % (name,))
            prnt('  return (%s) <= 0;' % (name,))
            prnt('}')
        else:
            prnt('static void %s(char *o)' % funcname)
            prnt('{')
            prnt('  *(%s)o = %s;' % (tp.get_c_name('*'), name))
            prnt('}')
        prnt()

    def _generate_cpy_constant_collecttype(self, tp, name):
        is_int = isinstance(tp, model.PrimitiveType) and tp.is_integer_type()
        if not is_int:
            self._do_collect_type(tp)

    def _generate_cpy_constant_decl(self, tp, name):
        is_int = isinstance(tp, model.PrimitiveType) and tp.is_integer_type()
        self._generate_cpy_const(is_int, name, tp)

    def _generate_cpy_constant_ctx(self, tp, name):
        is_int = isinstance(tp, model.PrimitiveType) and tp.is_integer_type()
        if not is_int:
            type_index = self._typesdict[tp]
            type_op = '_CFFI_OP(_CFFI_OP_CONSTANT, %d)' % type_index
        else:
            type_op = '_CFFI_OP(_CFFI_OP_CONSTANT_INT, 0)'
        self._lsts["global"].append(
            '  { "%s", _cffi_const_%s, %s },' % (name, name, type_op))

    # ----------
    # macros: for now only for integers

    def _generate_cpy_macro_collecttype(self, tp, name):
        pass

    def _generate_cpy_macro_decl(self, tp, name):
        if tp == '...':
            check_value = None
        else:
            check_value = tp     # an integer
        self._generate_cpy_const(True, name, check_value=check_value)

    def _generate_cpy_macro_ctx(self, tp, name):
        self._lsts["global"].append(
            '  { "%s", _cffi_const_%s, _CFFI_OP(_CFFI_OP_CONSTANT_INT, 0) },' %
            (name, name))

    # ----------
    # global variables

    def _generate_cpy_variable_collecttype(self, tp, name):
        self._do_collect_type(tp)

    def _generate_cpy_variable_decl(self, tp, name):
        pass

    def _generate_cpy_variable_ctx(self, tp, name):
        type_index = self._typesdict[tp]
        self._lsts["global"].append(
            '  { "%s", &%s, _CFFI_OP(_CFFI_OP_GLOBAL_VAR, %d)},'
            % (name, name, type_index))

    # ----------
    # emitting the opcodes for individual types

    def _emit_bytecode_PrimitiveType(self, tp, index):
        prim_index = PRIMITIVE_TO_INDEX[tp.name]
        self.cffi_types[index] = CffiOp(OP_PRIMITIVE, prim_index)

    def _emit_bytecode_RawFunctionType(self, tp, index):
        self.cffi_types[index] = CffiOp(OP_FUNCTION, self._typesdict[tp.result])
        index += 1
        for tp1 in tp.args:
            realindex = self._typesdict[tp1]
            if index != realindex:
                if isinstance(tp1, model.PrimitiveType):
                    self._emit_bytecode_PrimitiveType(tp1, index)
                else:
                    self.cffi_types[index] = CffiOp(OP_NOOP, realindex)
            index += 1
        self.cffi_types[index] = CffiOp(OP_FUNCTION_END, int(tp.ellipsis))

    def _emit_bytecode_PointerType(self, tp, index):
        self.cffi_types[index] = CffiOp(OP_POINTER, self._typesdict[tp.totype])

    _emit_bytecode_ConstPointerType = _emit_bytecode_PointerType

    def _emit_bytecode_FunctionPtrType(self, tp, index):
        raw = tp.as_raw_function()
        self.cffi_types[index] = CffiOp(OP_POINTER, self._typesdict[raw])

    def _emit_bytecode_ArrayType(self, tp, index):
        item_index = self._typesdict[tp.item]
        if tp.length is None:
            self.cffi_types[index] = CffiOp(OP_OPEN_ARRAY, item_index)
        else:
            assert self.cffi_types[index + 1] == 'LEN'
            self.cffi_types[index] = CffiOp(OP_ARRAY, item_index)
            self.cffi_types[index + 1] = CffiOp(None, '%d' % (tp.length,))

def make_c_source(ffi, module_name, preamble, target_c_file):
    recompiler = Recompiler(ffi, module_name)
    recompiler.collect_type_table()
    with open(target_c_file, 'w') as f:
        recompiler.write_source_to_f(f, preamble)

def _get_extension(module_name, c_file, kwds):
    source_name = ffiplatform.maybe_relative_path(c_file)
    include_dirs = kwds.setdefault('include_dirs', [])
    include_dirs.insert(0, '.')   # XXX
    return ffiplatform.get_extension(source_name, module_name, **kwds)

def recompile(ffi, module_name, preamble, tmpdir=None, **kwds):
    if tmpdir is None:
        tmpdir = 'build'
        if not os.path.isdir(tmpdir):
            os.mkdir(tmpdir)
    c_file = os.path.join(tmpdir, module_name + '.c')
    ext = _get_extension(module_name, c_file, kwds)
    make_c_source(ffi, module_name, preamble, c_file)
    outputfilename = ffiplatform.compile(tmpdir, ext)
    return outputfilename

def verify2(ffi, module_name, preamble, *args, **kwds):
    import imp
    assert module_name not in sys.modules, "module name conflict: %r" % (
        module_name,)
    outputfilename = recompile(ffi, module_name, preamble, *args, **kwds)
    module = imp.load_dynamic(module_name, outputfilename)
    return module.ffi, module.lib

def verify(ffi, module_name, preamble, *args, **kwds):
    ffi2, lib = verify2(ffi, module_name, preamble, *args, **kwds)
    ffi._verified(ffi2)
    return lib
