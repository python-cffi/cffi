import py
import subprocess
from ffi import FFI


SOURCE = """\
#include <errno.h>

int test_getting_errno(void) {
    errno = 123;
    return -1;
}

int test_setting_errno(void) {
    return errno;
}
"""

def setup_module(mod):
    from testing.udir import udir
    udir.join('testownlib.c').write(SOURCE)
    subprocess.check_call('gcc testownlib.c -shared -fPIC -o testownlib.so',
                          cwd=str(udir), shell=True)
    mod.module = str(udir.join('testownlib.so'))

def test_getting_errno():
    ffi = FFI()
    ffi.cdef("""
        int test_getting_errno(void);
    """)
    ownlib = ffi.load(module)
    res = ownlib.test_getting_errno()
    assert res == -1
    assert ffi.C.errno == 123

def test_setting_errno():
    ffi = FFI()
    ffi.cdef("""
        int test_setting_errno(void);
    """)
    ownlib = ffi.load(module)
    ffi.C.errno = 42
    res = ownlib.test_setting_errno()
    assert res == 42
