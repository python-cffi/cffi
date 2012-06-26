import py
from testing import backend_tests
from cffi.backend_ctypes import CTypesBackend


class TestCTypes(backend_tests.BackendTests):
    # for individual tests see
    # ====> backend_tests.py
    
    Backend = CTypesBackend
    TypeRepr = "<class 'ffi.CData<%s>'>"

    def test_array_of_func_ptr(self):
        py.test.skip("ctypes backend: not supported: "
                     "initializers for function pointers")
