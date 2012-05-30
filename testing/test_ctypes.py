from testing import backend_tests
from ffi.backend_ctypes import CTypesBackend


class TestCTypes(backend_tests.BackendTests):
    Backend = CTypesBackend
    TypeRepr = "<class 'ffi.CData<%s>'>"
