import py, sys, os
import _cffi_backend
from testing.support import is_musl

def test_no_unknown_exported_symbols():
    if not hasattr(_cffi_backend, '__file__'):
        py.test.skip("_cffi_backend module is built-in")
    if not sys.platform.startswith('linux') or is_musl:
        py.test.skip("linux-only")
    g = os.popen("objdump -T '%s'" % _cffi_backend.__file__, 'r')
    for line in g:
        if not line.startswith('0'):
            continue
        if line[line.find(' ') + 1] == 'l':
            continue
        if '*UND*' in line:
            continue
        name = line.split()[-1]
        if name.startswith('_') or name.startswith('.'):
            continue
        # a statically-linked libffi will always appear here without header hackage, ignore it if it's internal
        if name.startswith('ffi_') and 'Base' in line:
            continue
        if name not in ('init_cffi_backend', 'PyInit__cffi_backend', 'cffistatic_ffi_call'):
            raise Exception("Unexpected exported name %r" % (name,))
    g.close()
