import os
from . import ffiplatform

class Verifier(object):

    def _write_printf(f, what, *args):
        if not args:
            f.write('  printf("%s\\n");\n' % (what,))
        else:
            f.write('  printf("%s\\n", %s);\n' % (what, ', '.join(args)))

    def verify(self, ffi, preamble, **kwargs):
        tst_file_base = ffiplatform._get_test_file_base()
        with open(tst_file_base + '.c', 'w') as f:
            f.write('#include <stdio.h>\n')
            f.write('#include <stdint.h>\n')
            f.write('#include <stddef.h>\n')
            f.write(preamble + "\n\n")
            f.write('int main() {\n')
            for name, tp in ffi._parser._declarations.iteritems():
                kind, realname = name.split(' ', 1)
                tp.verifier_declare(self, kind, realname, f)
            f.write('  return 0;\n')
            f.write('}\n')
        err = os.system('gcc -Werror -c %s.c -o %s.o' %
                        (tst_file_base, tst_file_base))
        if err:
            raise ffiplatform.VerificationError(
                '%s.c: see compilation warnings and errors above' %
                (tst_file_base,))
