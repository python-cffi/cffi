import sys

import py

if '__pypy__' in sys.modules:
    py.test.skip("C backend tests are CPython only")

from testing import backend_tests
import _ffi_backend


class TestFFI(backend_tests.BackendTests):
    TypeRepr = "<ctype '%s'>"

    @staticmethod
    def Backend():
        return _ffi_backend
