# Integrated from the cffi-buildtool project by Rose Davidson
# (https://github.com/inklesspen/cffi-buildtool), MIT-licensed.
import io

from ..api import FFI


def _execfile(pysrc, filename, globs):
    compiled = compile(source=pysrc, filename=filename, mode='exec')
    exec(compiled, globs, globs)


def find_ffi_in_python_script(pysrc, filename, ffivar):
    """Execute ``pysrc`` and return the :class:`FFI` object it defines.

    The script is executed with ``__name__`` set to ``"gen-cffi-src"``,
    so a trailing ``if __name__ == "__main__": ffibuilder.compile()``
    block in the script is skipped.

    ``ffivar`` is the name bound by the script to the :class:`FFI`
    object, or to a callable that returns one.

    Raises :class:`NameError` if the name is not bound by the script,
    or :class:`TypeError` if the name does not resolve to an
    :class:`FFI` instance.
    """
    globs = {'__name__': 'gen-cffi-src'}
    _execfile(pysrc, filename, globs)
    if ffivar not in globs:
        raise NameError(
            "Expected to find the FFI object with the name %r, "
            "but it was not found." % (ffivar,)
        )
    ffi = globs[ffivar]
    if not isinstance(ffi, FFI) and callable(ffi):
        # Maybe it's a callable that returns a FFI
        ffi = ffi()
    if not isinstance(ffi, FFI):
        raise TypeError(
            "Found an object with the name %r but it was not an "
            "instance of cffi.api.FFI" % (ffivar,)
        )
    return ffi


def make_ffi_from_sources(modulename, cdef, csrc):
    """Build an :class:`FFI` from ``cdef`` text and a C source prelude."""
    ffibuilder = FFI()
    ffibuilder.cdef(cdef)
    ffibuilder.set_source(modulename, csrc)
    return ffibuilder


def generate_c_source(ffi):
    """Return the C source that :meth:`FFI.emit_c_code` would write."""
    output = io.StringIO()
    ffi.emit_c_code(output)
    return output.getvalue()
