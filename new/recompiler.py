import os
from cffi1 import ffiplatform, model
from cffi_opcode import *


class Recompiler:

    def __init__(self, ffi):
        self.ffi = ffi

    def collect_type_table(self):
        self._typesdict = {}
        self._generate('collecttype')
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

    def _generate_cpy_function_collecttype(self, tp, name):
        self._do_collect_type(tp.as_raw_function())

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
        self.cffi_types[index] = CffiOp(OP_FUNCTION_END, tp.ellipsis)

    def _emit_bytecode_PointerType(self, tp, index):
        self.cffi_types[index] = CffiOp(OP_POINTER, self._typesdict[tp.totype])

    # ----------

    def _prnt(self, what=''):
        self._f.write(what + '\n')

    def write_source_to_f(self, f, preamble):
        self._f = f
        prnt = self._prnt
        # first copy some standard set of lines that are mostly '#define'
        filename = os.path.join(os.path.dirname(__file__), '_cffi_include.h')
        with open(filename, 'r') as g:
            prnt(g.read())
        prnt('/************************************************************/')
        prnt()
        # then paste the C source given by the user, verbatim.
        prnt(preamble)
        prnt()
        #...
        

def make_c_source(ffi, target_c_file, preamble):
    recompiler = Recompiler(ffi)
    recompiler.collect_type_table()
    with open(target_c_file, 'w') as f:
        recompiler.write_source_to_f(f, preamble)
