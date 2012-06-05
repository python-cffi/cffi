
import py
from cffi import FFI, VerificationMissing

def test_ffi_nonfull_struct():
    py.test.skip("XXX")
    ffi = FFI()
    ffi.cdef("""
    struct sockaddr {
       int sa_family;
       ...;
    };
    """)
    py.test.raises(VerificationMissing, ffi.sizeof, 'struct sockaddr')
    ffi.verify('''
    #include <sys/types.h>
    #include <sys/socket.h>
    ''')
    assert ffi.sizeof('struct sockaddr') == 14 + ffi.sizeof(int)
