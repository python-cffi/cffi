
from platformer import udir, platform, ExternalCompilationInfo

EXAMPLES = {
    'double' : '1.5e15',
}

class Verifier(object):
    def __init__(self):
        self.rescount = 0
        self.decl_lines = []
        self.call_lines = []
    
    def verify(self, ffi, preamble, **kwargs):
        tst_file = udir.join('test.c')
        i = 0
        while tst_file.check():
            tst_file = udir.join('test%d.c' % i)
            i += 1
        for name, decl in ffi._declarations.iteritems():
            if name.startswith('function '):
                self._declare_function(decl)
        with tst_file.open('w') as f:
            f.write(preamble + "\n\n")
            f.write('int main() {\n')
            for line in self.decl_lines + self.call_lines:
                f.write('  ' + line + "\n")
            f.write('}\n')
        f.close()
        platform.compile([str(tst_file)], ExternalCompilationInfo(**kwargs))

    def _example(self, tpname):
        return EXAMPLES[tpname]

    def _declare_function(self, decl):
        funcname = decl.type.declname
        restype = decl.type.type.names[0]
        if decl.args is None:
            args = ''
        else:
            args = []
            for arg in decl.args.params:
                args.append(self._example(arg.type.type.names[0]))
            args = ', '.join(args)
        if restype == 'void':
            self.call_lines.append('  %s(%s);' % (funcname, args))
        else:
            call = '  res%d = %s(%s);' % (self.rescount, funcname, args)
            self.call_lines.append(call)
            self.decl_lines.append('  %s res%d;' % (restype, self.rescount))
            self.rescount += 1

