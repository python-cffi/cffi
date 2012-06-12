import os
from . import ffiplatform

class Verifier(object):

    def __init__(self, ffi):
        self.ffi = ffi

    def write(self, what):
        print >> self.f, '  ' + what

    def write_printf(self, what, *args):
        self.has_printf = True
        if not args:
            print >> self.f, '  printf("%s\\n");' % (what,)
        else:
            print >> self.f, '  printf("%s\\n", %s);' % (
                what, ', '.join(args))

    def verify(self, preamble, **kwargs):
        tst_file_base = ffiplatform._get_test_file_base()
        self.has_printf = False
        with open(tst_file_base + '.c', 'w') as f:
            f.write("""\
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <unistd.h>

#define __sameconstant__(x, y) \\
  { int result[1-2*((x)-(y))*((x)-(y))]; }

#define __sametype__(ppresult, typename) \\
  { ppresult = (typename**)0; }

""")
            f.write(preamble + "\n\n")
            f.write('int main() {\n')
            self.f = f
            for name, tp in self.ffi._parser._declarations.iteritems():
                kind, realname = name.split(' ', 1)
                method = getattr(tp, 'verifier_declare_' + kind)
                method(self, realname)
            del self.f
            f.write('  return 0;\n')
            f.write('}\n')
        err = os.system('gcc -Werror -S %s.c -o %s.s' %
                        (tst_file_base, tst_file_base))
        if err:
            raise ffiplatform.VerificationError(
                '%s.c: see compilation warnings and errors above' %
                (tst_file_base,))
