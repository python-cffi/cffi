
import py
from ffi import FFI

def test_ffi_nonfull_struct():
    py.test.skip("not implemented")
    ffi = FFI()
    ffi.cdef("""
    struct sockaddr {
       int sa_family;
       ...
    }
    """)
    
