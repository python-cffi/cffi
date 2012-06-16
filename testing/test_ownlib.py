import py, sys
import subprocess
from cffi import FFI
from cffi.backend_ctypes import CTypesBackend


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

class TestOwnLib(object):
    Backend = CTypesBackend

    def setup_class(cls):
        if sys.platform == 'win32':
            return
        from testing.udir import udir
        udir.join('testownlib.c').write(SOURCE)
        subprocess.check_call(
            'gcc testownlib.c -shared -fPIC -o testownlib.so',
            cwd=str(udir), shell=True)
        cls.module = str(udir.join('testownlib.so'))

    def test_getting_errno(self):
        if sys.platform == 'win32':
            py.test.skip("fix the auto-generation of the tiny test lib")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_getting_errno(void);
        """)
        ownlib = ffi.dlopen(self.module)
        res = ownlib.test_getting_errno()
        assert res == -1
        assert ffi.errno == 123

    def test_setting_errno(self):
        if sys.platform == 'win32':
            py.test.skip("fix the auto-generation of the tiny test lib")
        if self.Backend is CTypesBackend and '__pypy__' in sys.modules:
            py.test.skip("XXX errno issue with ctypes on pypy?")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_setting_errno(void);
        """)
        ownlib = ffi.dlopen(self.module)
        ffi.errno = 42
        res = ownlib.test_setting_errno()
        assert res == 42
        assert ffi.errno == 42
