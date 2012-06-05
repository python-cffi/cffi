from testing import backend_tests
from cffi.backend_ctypes import CTypesBackend


class TestCTypes(backend_tests.BackendTests):
    # for individual tests see
    # ====> backend_tests.py
    
    Backend = CTypesBackend
    TypeRepr = "<class 'ffi.CData<%s>'>"
