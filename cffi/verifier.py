import os
from . import model, ffiplatform

class Verifier(object):

    def __init__(self, ffi):
        self.ffi = ffi

    def prnt(self, what=''):
        print >> self.f, what

##    def write_printf(self, what, *args):
##        if not args:
##            print >> self.f, '  printf("%s\\n");' % (what,)
##        else:
##            print >> self.f, '  printf("%s\\n", %s);' % (
##                what, ', '.join(args))

    def verify(self, preamble, **kwargs):
        modname = ffiplatform.undercffi_module_name()
        filebase = os.path.join(ffiplatform.tmpdir(), modname)
        
        with open(filebase + 'module.c', 'w') as f:
            self.f = f
            self.prnt("#include <Python.h>")
            self.prnt()
            self.prnt('#define _cffi_from_c_double PyFloat_FromDouble')
            self.prnt('#define _cffi_to_c_double PyFloat_AsDouble')
            self.prnt('#define _cffi_from_c_float PyFloat_FromDouble')
            self.prnt('#define _cffi_to_c_float PyFloat_AsDouble')
            self.prnt()
            self.prnt(preamble)
            self.prnt()
            #
            self.generate("decl")
            #
            self.prnt('static PyMethodDef _cffi_methods[] = {')
            self.generate("method")
            self.prnt('  {NULL, NULL}    /* Sentinel */')
            self.prnt('};')
            self.prnt()
            #
            self.prnt('void init%s()' % modname)
            self.prnt('{')
            self.prnt('  Py_InitModule("%s", _cffi_methods);' % modname)
            self.prnt('  if (PyErr_Occurred()) return;')
            self.generate("init")
            self.prnt('}')
            #
            del self.f

        # XXX use more distutils?
        import distutils.sysconfig
        python_h = distutils.sysconfig.get_python_inc()
        err = os.system("gcc -I'%s' -O2 -shared %smodule.c -o %s.so" %
                        (python_h, filebase, filebase))
        if err:
            raise ffiplatform.VerificationError(
                '%smodule.c: see compilation errors above' % (filebase,))
        #
        import imp
        try:
            return imp.load_dynamic(modname, '%s.so' % filebase)
        except ImportError, e:
            raise ffiplatform.VerificationError(str(e))

    def generate(self, step_name):
        for name, tp in self.ffi._parser._declarations.iteritems():
            kind, realname = name.split(' ', 1)
            method = getattr(self, 'generate_cpy_%s_%s' % (kind, step_name))
            method(tp, realname)

    def generate_nothing(self, tp, name):
        pass

    # ----------

    def convert_to_c(self, tp, fromvar, tovar, errcode):
        if isinstance(tp, model.PrimitiveType):
            self.prnt('  %s = _cffi_to_c_%s(%s);' % (
                tovar, tp.name.replace(' ', '_'), fromvar))
            self.prnt('  if (%s == (%s)-1 && PyErr_Occurred())' % (
                tovar, tp.name))
            self.prnt('    %s;' % errcode)
        else:
            raise NotImplementedError(tp)

    def get_converter_from_c(self, tp):
        if isinstance(tp, model.PrimitiveType):
            return '_cffi_from_c_%s' % (tp.name.replace(' ', '_'),)
        else:
            raise NotImplementedError(tp)

    # ----------

    # XXX
    generate_cpy_typedef_decl   = generate_nothing
    generate_cpy_typedef_method = generate_nothing
    generate_cpy_typedef_init   = generate_nothing

    # ----------

    def generate_cpy_function_decl(self, tp, name):
        assert isinstance(tp, model.FunctionType)
        prnt = self.prnt
        numargs = len(tp.args)
        if numargs == 0:
            argname = 'no_arg'
        elif numargs == 1:
            argname = 'arg0'
        else:
            argname = 'args'
        prnt('static PyObject *_cffi_f_%s(PyObject *self, PyObject *%s)' %
             (name, argname))
        prnt('{')
        assert not tp.ellipsis  # XXX later
        #
        for i, type in enumerate(tp.args):
            prnt('  %s;' % type.get_c_name(' x%d' % i))
        if not isinstance(tp.result, model.VoidType):
            result_code = 'result = '
            prnt('  %s;' % tp.result.get_c_name(' result'))
        else:
            result_code = ''
        #
        if len(tp.args) > 1:
            rng = range(len(tp.args))
            for i in rng:
                prnt('  PyObject *arg%d;' % i)
            prnt()
            prnt('  if (!PyArg_ParseTuple("%s:%s", %s)) {' % (
                'O' * numargs, name, ', '.join(['&arg%d' % i for i in rng])))
            prnt('    return NULL;')
        prnt()
        #
        for i, type in enumerate(tp.args):
            self.convert_to_c(type, 'arg%d' % i, 'x%d' % i, 'return NULL')
            prnt()
        #
        prnt('  { %s%s(%s); }' % (
            result_code, name,
            ', '.join(['x%d' % i for i in range(len(tp.args))])))
        prnt()
        #
        if result_code:
            prnt('  return %s(result);' % self.get_converter_from_c(tp.result))
        else:
            prnt('  Py_INCREF(Py_None);')
            prnt('  return Py_None;')
        prnt('}')
        prnt()

    def generate_cpy_function_method(self, tp, name):
        numargs = len(tp.args)
        if numargs == 0:
            meth = 'METH_NOARGS'
        elif numargs == 1:
            meth = 'METH_O'
        else:
            meth = 'METH_VARARGS'
        self.prnt('  {"%s", _cffi_f_%s, %s},' % (name, name, meth))

    generate_cpy_function_init = generate_nothing
