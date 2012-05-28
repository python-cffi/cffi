from testing import backend_tests
import _ffi_backend


class TestFFI(backend_tests.BackendTests):

    @staticmethod
    def Backend():
        return _ffi_backend
