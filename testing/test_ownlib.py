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

class TestOwnLib(object):
    from ffi.backend_ctypes import CTypesBackend as Backend

    def setup_class(cls):
        from testing.udir import udir
        udir.join('testownlib.c').write(SOURCE)
        subprocess.check_call(
            'gcc testownlib.c -shared -fPIC -o testownlib.so',
            cwd=str(udir), shell=True)
        cls.module = str(udir.join('testownlib.so'))

    def test_getting_errno(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_getting_errno(void);
        """)
        ownlib = ffi.load(self.module)
        res = ownlib.test_getting_errno()
        assert res == -1
        assert ffi.C.errno == 123

    def test_setting_errno(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            int test_setting_errno(void);
        """)
        ownlib = ffi.load(self.module)
        ffi.C.errno = 42
        res = ownlib.test_setting_errno()
        assert res == 42
