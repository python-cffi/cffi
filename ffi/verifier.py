
from platformer import platform, ExternalCompilationInfo
from ffi import ffiplatform

def _write_printf(f, what, *args):
    if not args:
        f.write('  printf("%s\\n");\n' % (what,))
    else:
        f.write('  printf("%s\\n", %s);\n' % (what, ', '.join(args)))

class Verifier(object):
    def __init__(self):
        self.rescount = 0
    
    def verify(self, ffi, preamble, **kwargs):
        tst_file = ffiplatform._get_test_file()
        with tst_file.open('w') as f:
            f.write('#include <stdio.h>\n')
            f.write(preamble + "\n\n")
            f.write('int main() {\n')
            for name, tp in ffi._parser._declarations.iteritems():
                tp.declare(f)
            f.write('  return 0;\n')
            f.write('}\n')
        f.close()
        exe_name = platform.compile([str(tst_file)],
                                    ExternalCompilationInfo(**kwargs))
        out = platform.execute(exe_name)
        assert out.returncode == 0
        outlines = out.out.splitlines()

    def _declare_function(self, f, tp):
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

    def _declare_struct(self, f, decl):
        structname = decl.name
        _write_printf(f, 'BEGIN struct %s size(%%ld)' % structname,
                      'sizeof(struct %s)' % structname)
        for decl in decl.decls:
            pass
            #_write_printf(f, 'FIELD ofs(%s) size(%s)')
        _write_printf(f, 'END struct %s' % structname)
