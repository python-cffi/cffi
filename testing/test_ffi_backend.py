import sys

import py

if '__pypy__' in sys.modules:
    py.test.skip("C backend tests are CPython only")

from testing import backend_tests, test_function, test_ownlib
import _cffi_backend


class TestFFI(backend_tests.BackendTests,
              test_function.TestFunction,
              test_ownlib.TestOwnLib):
    TypeRepr = "<ctype '%s'>"

    @staticmethod
    def Backend():
        return _cffi_backend
