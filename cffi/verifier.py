import os
from . import ffiplatform

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

    def generate(self, step_name):
        for name, tp in self.ffi._parser._declarations.iteritems():
            kind, realname = name.split(' ', 1)
            method = getattr(tp, 'generate_cpy_%s_%s' % (kind, step_name), 0)
            if method:
                method(self, realname)

    def verify(self, preamble, **kwargs):
        modname = ffiplatform.undercffi_module_name()
        filebase = os.path.join(ffiplatform.tmpdir(), modname)
        
        with open(filebase + 'module.c', 'w') as f:
            self.f = f
            self.prnt("#include <Python.h>")
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
