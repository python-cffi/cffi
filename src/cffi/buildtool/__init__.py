"""Helpers for generating CFFI C source without invoking external dependencies.

This subpackage exposes a small API and a command-line entry point
(``gen-cffi-src``) that build backends can invoke during a build to
produce the ``.c`` source file for a CFFI extension module.:

* :func:`find_ffi_in_python_script` -- execute an "exec-python" build
  script and return the :class:`cffi.FFI` object it defines.
* :func:`make_ffi_from_sources` -- construct an :class:`cffi.FFI`
  from a ``cdef`` string and a C source prelude.
* :func:`generate_c_source` -- emit the generated C source for an
  :class:`cffi.FFI` as a string.

"""

from ._gen import (
    find_ffi_in_python_script,
    generate_c_source,
    make_ffi_from_sources,
)

__all__ = [
    'find_ffi_in_python_script',
    'generate_c_source',
    'make_ffi_from_sources',
]
