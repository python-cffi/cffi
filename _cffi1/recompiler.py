import os, sys
from cffi import ffiplatform, model
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
        # collect all structs and unions
        self._struct_unions = {}
        for tp in all_decls:
            if isinstance(tp, model.StructOrUnion):
                self._struct_unions[tp] = None
        for i, tp in enumerate(sorted(self._struct_unions,
                                      key=lambda tp: tp.name)):
            self._struct_unions[tp] = i
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
            elif isinstance(tp, model.StructOrUnion):
                if tp.fldtypes is not None:
                    for name1, tp1 in zip(tp.fldnames, tp.fldtypes):
                        self._do_collect_type(self._field_type(tp, name1, tp1))
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

    def _gettypenum(self, type):
        # a KeyError here is a bug.  please report it! :-)
        return self._typesdict[type]

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
        self.cffi_types = tuple(self.cffi_types)    # don't change any more
        typeindex2type = dict([(i, tp) for (tp, i) in self._typesdict.items()])
        for i, op in enumerate(self.cffi_types):
            comment = ''
            if i in typeindex2type:
                comment = ' // ' + typeindex2type[i]._get_c_name()
            prnt('/* %2d */ %s,%s' % (i, op.as_c_expr(), comment))
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
        ALL_STEPS = ["global", "field", "struct_union", "enum", "typename"]
        nums = {}
        self._lsts = {}
        for step_name in ALL_STEPS:
            self._lsts[step_name] = []
        self._seen_struct_unions = set()
        self._generate("ctx")
        self._add_missing_struct_unions()
        for step_name in ALL_STEPS:
            lst = self._lsts[step_name]
            nums[step_name] = len(lst)
            if nums[step_name] > 0:
                lst.sort()  # sort by name, which is at the start of each line
                prnt('static const struct _cffi_%s_s _cffi_%ss[] = {' % (
                    step_name, step_name))
                if step_name == 'field':
                    self._fix_final_field_list(lst)
                for line in lst:
                    prnt(line)
                prnt('};')
                prnt()
        #
        # check for a possible internal inconsistency: _cffi_struct_unions
        # should have been generated with exactly self._struct_unions
        lst = self._lsts["struct_union"]
        for tp, i in self._struct_unions.items():
            assert i < len(lst)
            assert lst[i].startswith('  { "%s"' % tp.name)
        assert len(lst) == len(self._struct_unions)
        #
        # the declaration of '_cffi_type_context'
        prnt('static const struct _cffi_type_context_s _cffi_type_context = {')
        prnt('  _cffi_types,')
        for step_name in ALL_STEPS:
            if nums[step_name] > 0:
                prnt('  _cffi_%ss,' % step_name)
            else:
                prnt('  NULL,  /* no %ss */' % step_name)
        for step_name in ALL_STEPS:
            if step_name != "field":
                prnt('  %d,  /* num_%ss */' % (nums[step_name], step_name))
        prnt('};')
        prnt()
        #
        # the init function, loading _cffi_backend and calling a method there
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
        if getattr(tp, "origin", None) == "unknown_type":
            self._struct_ctx(tp, tp.name, approxname=None)
        elif isinstance(tp, model.NamedPointerType):
            self._struct_ctx(tp.totype, tp.totype.name, approxname=None)

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
    # named structs or unions

    def _field_type(self, tp_struct, field_name, tp_field):
        if isinstance(tp_field, model.ArrayType) and tp_field.length == '...':
            ptr_struct_name = tp_struct.get_c_name('*')
            actual_length = '_cffi_array_len(((%s)0)->%s)' % (
                ptr_struct_name, field_name)
            tp_field = tp_field.resolve_length(actual_length)
        return tp_field

    def _struct_collecttype(self, tp):
        self._do_collect_type(tp)

    def _struct_decl(self, tp, cname, approxname):
        if tp.fldtypes is None:
            return
        prnt = self._prnt
        checkfuncname = '_cffi_checkfld_%s' % (approxname,)
        prnt('__attribute__((unused))')
        prnt('static void %s(%s *p)' % (checkfuncname, cname))
        prnt('{')
        prnt('  /* only to generate compile-time warnings or errors */')
        prnt('  (void)p;')
        for fname, ftype, fbitsize in tp.enumfields():
            if (isinstance(ftype, model.PrimitiveType)
                and ftype.is_integer_type()) or fbitsize >= 0:
                # accept all integers, but complain on float or double
                prnt('  (void)((p->%s) << 1);' % fname)
            else:
                # only accept exactly the type declared.
                try:
                    prnt('  { %s = &p->%s; (void)tmp; }' % (
                        ftype.get_c_name('*tmp', 'field %r'%fname), fname))
                except ffiplatform.VerificationError as e:
                    prnt('  /* %s */' % str(e))   # cannot verify it, ignore
        prnt('}')
        prnt('struct _cffi_align_%s { char x; %s y; };' % (approxname, cname))
        prnt()

    def _struct_ctx(self, tp, cname, approxname):
        type_index = self._typesdict[tp]
        flags = []
        if tp.partial:
            flags.append('CT_CUSTOM_FIELD_POS')
        if isinstance(tp, model.UnionType):
            flags.append('CT_UNION')
        flags = ('|'.join(flags)) or '0'
        if tp.fldtypes is not None:
            c_field = [approxname]
            for fldname, fldtype, fbitsize in tp.enumfields():
                fldtype = self._field_type(tp, fldname, fldtype)
                spaces = " " * len(fldname)
                # cname is None for _add_missing_struct_unions() only
                op = '_CFFI_OP_NOOP'
                if fbitsize >= 0:
                    op = '_CFFI_OP_BITFIELD'
                    size = '%d /* bits */' % fbitsize
                elif cname is None or (
                        isinstance(fldtype, model.ArrayType) and
                        fldtype.length is None):
                    size = '(size_t)-1'
                else:
                    size = 'sizeof(((%s)0)->%s)' % (tp.get_c_name('*'), fldname)
                if cname is None or fbitsize >= 0:
                    offset = '(size_t)-1'
                else:
                    offset = 'offsetof(%s, %s)' % (tp.get_c_name(''), fldname)
                c_field.append(
                    '  { "%s", %s,\n' % (fldname, offset) +
                    '     %s   %s,\n' % (spaces, size) +
                    '     %s   _CFFI_OP(%s, %s) },' % (
                            spaces, op, self._typesdict[fldtype]))
            self._lsts["field"].append('\n'.join(c_field))
            #
            if cname is None:  # unknown name, for _add_missing_struct_unions
                size_align = (' (size_t)-2, -2, /* unnamed */\n' +
                    '    _cffi_FIELDS_FOR_%s, %d },' % (approxname,
                                                        len(tp.fldtypes),))
            else:
                size_align = ('\n' +
                    '    sizeof(%s),\n' % (cname,) +
                    '    offsetof(struct _cffi_align_%s, y),\n'% (approxname,) +
                    '    _cffi_FIELDS_FOR_%s, %d },' % (approxname,
                                                        len(tp.fldtypes),))
        else:
            size_align = ' (size_t)-1, -1, -1, 0 /* opaque */ },'
        self._lsts["struct_union"].append(
            '  { "%s", %d, %s,' % (tp.name, type_index, flags) + size_align)
        self._seen_struct_unions.add(tp)

    def _add_missing_struct_unions(self):
        # not very nice, but some struct declarations might be missing
        # because they don't have any known C name.  Check that they are
        # not partial (we can't complete or verify them!) and emit them
        # anonymously.
        for tp in list(self._struct_unions):
            if tp not in self._seen_struct_unions:
                if tp.partial:
                    raise NotImplementedError("internal inconsistency: %r is "
                                              "partial but was not seen at "
                                              "this point" % (tp,))
                assert tp.name.startswith('$') and tp.name[1:].isdigit()
                self._struct_ctx(tp, None, tp.name[1:])

    def _fix_final_field_list(self, lst):
        count = 0
        for i in range(len(lst)):
            struct_fields = lst[i]
            pname = struct_fields.split('\n')[0]
            define_macro = '#define _cffi_FIELDS_FOR_%s  %d' % (pname, count)
            lst[i] = define_macro + struct_fields[len(pname):]
            count += lst[i].count('\n  { "')

    def _generate_cpy_struct_collecttype(self, tp, name):
        self._struct_collecttype(tp)
    _generate_cpy_union_collecttype = _generate_cpy_struct_collecttype

    def _generate_cpy_struct_decl(self, tp, name):
        cname = tp._get_c_name()
        if ' ' in cname:
            prefix, declname = cname.split(' ', 1)
        else:
            prefix, declname = '', cname
        while declname.startswith('$'):
            prefix += 'D'
            declname = declname[1:]
        approxname = prefix + '_' + declname
        assert '$' not in approxname
        self._struct_decl(tp, cname, approxname)
    _generate_cpy_union_decl = _generate_cpy_struct_decl

    def _generate_cpy_struct_ctx(self, tp, name, prefix='s'):
        cname = tp.get_c_name('')
        self._struct_ctx(tp, cname, cname.replace(' ', '_'))
    _generate_cpy_union_ctx = _generate_cpy_struct_ctx

    # ----------
    # 'anonymous' declarations.  These are produced for anonymous structs
    # or unions; the 'name' is obtained by a typedef.

    def _generate_cpy_anonymous_collecttype(self, tp, name):
        if isinstance(tp, model.EnumType):
            self._generate_cpy_enum_collecttype(tp, name)
        else:
            self._struct_collecttype(tp)

    def _generate_cpy_anonymous_decl(self, tp, name):
        if isinstance(tp, model.EnumType):
            self._generate_cpy_enum_decl(tp, name, '')
        else:
            self._struct_decl(tp, name, 'typedef_' + name)

    def _generate_cpy_anonymous_ctx(self, tp, name):
        if isinstance(tp, model.EnumType):
            self._generate_cpy_enum_ctx(tp, name, '')
        else:
            self._struct_ctx(tp, name, 'typedef_' + name)

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

    def _global_type(self, tp, global_name):
        if isinstance(tp, model.ArrayType) and tp.length == '...':
            actual_length = '_cffi_array_len(%s)' % (global_name,)
            tp = tp.resolve_length(actual_length)
        return tp

    def _generate_cpy_variable_collecttype(self, tp, name):
        self._do_collect_type(self._global_type(tp, name))

    def _generate_cpy_variable_decl(self, tp, name):
        pass

    def _generate_cpy_variable_ctx(self, tp, name):
        tp = self._global_type(tp, name)
        type_index = self._typesdict[tp]
        self._lsts["global"].append(
            '  { "%s", &%s, _CFFI_OP(_CFFI_OP_GLOBAL_VAR, %d)},'
            % (name, name, type_index))

    # ----------
    # emitting the opcodes for individual types

    def _emit_bytecode_VoidType(self, tp, index):
        self.cffi_types[index] = CffiOp(OP_PRIMITIVE, PRIM_VOID)

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
    _emit_bytecode_NamedPointerType = _emit_bytecode_PointerType

    def _emit_bytecode_FunctionPtrType(self, tp, index):
        raw = tp.as_raw_function()
        self.cffi_types[index] = CffiOp(OP_POINTER, self._typesdict[raw])

    def _emit_bytecode_ArrayType(self, tp, index):
        item_index = self._typesdict[tp.item]
        if tp.length is None:
            self.cffi_types[index] = CffiOp(OP_OPEN_ARRAY, item_index)
        elif tp.length == '...':
            raise ffiplatform.VerificationError(
                "type %s badly placed: the '...' array length can only be "
                "used on global arrays or on fields of structures" % (
                    str(tp).replace('/*...*/', '...'),))
        else:
            assert self.cffi_types[index + 1] == 'LEN'
            self.cffi_types[index] = CffiOp(OP_ARRAY, item_index)
            self.cffi_types[index + 1] = CffiOp(None, str(tp.length))

    def _emit_bytecode_StructType(self, tp, index):
        struct_index = self._struct_unions[tp]
        self.cffi_types[index] = CffiOp(OP_STRUCT_UNION, struct_index)

    _emit_bytecode_UnionType = _emit_bytecode_StructType

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

def recompile(ffi, module_name, preamble, tmpdir='.', **kwds):
    c_file = os.path.join(tmpdir, module_name + '.c')
    ext = _get_extension(module_name, c_file, kwds)
    make_c_source(ffi, module_name, preamble, c_file)
    outputfilename = ffiplatform.compile(tmpdir, ext)
    return outputfilename

def verify(ffi, module_name, preamble, *args, **kwds):
    from _cffi1.udir import udir
    import imp
    assert module_name not in sys.modules, "module name conflict: %r" % (
        module_name,)
    outputfilename = recompile(ffi, module_name, preamble,
                               tmpdir=str(udir),
                               *args, **kwds)
    module = imp.load_dynamic(module_name, outputfilename)
    #
    # hack hack hack: copy all *bound methods* from module.ffi back to the
    # ffi instance.  Then calls like ffi.new() will invoke module.ffi.new().
    for name in dir(module.ffi):
        if not name.startswith('_'):
            attr = getattr(module.ffi, name)
            if attr is not getattr(ffi, name, object()):
                setattr(ffi, name, attr)
    return module.lib
