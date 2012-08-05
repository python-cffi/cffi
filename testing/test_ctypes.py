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

    def test_structptr_argument(self):
        py.test.skip("ctypes backend: not supported: passing a list "
                     "for a pointer argument")

    def test_array_argument_as_list(self):
        py.test.skip("ctypes backend: not supported: passing a list "
                     "for a pointer argument")

    def test_cast_to_array_type(self):
        py.test.skip("ctypes backend: not supported: casting to array")
