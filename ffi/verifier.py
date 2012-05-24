
from platformer import udir, platform, ExternalCompilationInfo

class Verifier(object):
    def __init__(self):
        self.rescount = 0
    
    def verify(self, ffi, preamble, **kwargs):
        tst_file = udir.join('test.c')
        i = 0
        while tst_file.check():
            tst_file = udir.join('test%d.c' % i)
            i += 1
        with tst_file.open('w') as f:
            f.write(preamble + "\n\n")
            f.write('int main() {\n')
            for name, decl in ffi._declarations.iteritems():
                if name.startswith('function '):
                    self._declare_function(f, decl)
            f.write('}\n')
        f.close()
        platform.compile([str(tst_file)], ExternalCompilationInfo(**kwargs))

    def _declare_function(self, f, decl):
        funcname = decl.type.declname
        restype = decl.type.type.names[0]
        if decl.args is None:
            args = ''
        else:
            args = []
            for arg in decl.args.params:
                args.append(arg.type.type.names[0])
            args = ', '.join(args)
        f.write('  %s(* res%d)(%s) = %s;\n' % (restype, self.rescount,
                                            args, funcname))
        self.rescount += 1
