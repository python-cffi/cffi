
from platformer import platform, ExternalCompilationInfo
from ffi import ffiplatform

class Verifier(object):
    def __init__(self):
        self.rescount = 0

    def _write_printf(f, what, *args):
        if not args:
            f.write('  printf("%s\\n");\n' % (what,))
        else:
            f.write('  printf("%s\\n", %s);\n' % (what, ', '.join(args)))

    def verify(self, ffi, preamble, **kwargs):
        tst_file = ffiplatform._get_test_file()
        with tst_file.open('w') as f:
            f.write('#include <stdio.h>\n')
            f.write(preamble + "\n\n")
            f.write('int main() {\n')
            for name, tp in ffi._parser._declarations.iteritems():
                tp.verifier_declare(self, f)
            f.write('  return 0;\n')
            f.write('}\n')
        f.close()
        exe_name = platform.compile([str(tst_file)],
                                    ExternalCompilationInfo(**kwargs))
        out = platform.execute(exe_name)
        assert out.returncode == 0
        outlines = out.out.splitlines()
