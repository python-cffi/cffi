import sys, os
from cffi._imp_emulation import load_dynamic

if sys.version_info < (3,):
    __all__ = ['u', 'arraytostring', 'load_dynamic']

    class U(object):
        def __add__(self, other):
            return eval('u'+repr(other).replace(r'\\u', r'\u')
                                       .replace(r'\\U', r'\U'))
    u = U()
    long = long     # for further "from testing.support import long"
    assert u+'a\x00b' == eval(r"u'a\x00b'")
    assert u+'a\u1234b' == eval(r"u'a\u1234b'")
    assert u+'a\U00012345b' == eval(r"u'a\U00012345b'")
    def arraytostring(a):
        return a.tostring()

else:
    __all__ = ['u', 'unicode', 'long', 'arraytostring', 'load_dynamic']
    u = ""
    unicode = str
    long = int
    def arraytostring(a):
        return a.tobytes()


class StdErrCapture(object):
    """Capture writes to sys.stderr (not to the underlying file descriptor)."""
    def __enter__(self):
        try:
            from StringIO import StringIO
        except ImportError:
            from io import StringIO
        self.old_stderr = sys.stderr
        sys.stderr = f = StringIO()
        if hasattr(sys, '__unraisablehook__'):           # work around pytest
            self.old_unraisablebook = sys.unraisablehook # on recent CPythons
            sys.unraisablehook = sys.__unraisablehook__
        return f
    def __exit__(self, *args):
        sys.stderr = self.old_stderr
        if hasattr(self, 'old_unraisablebook'):
            sys.unraisablehook = self.old_unraisablebook


class FdWriteCapture(object):
    """xxx limited to capture at most 512 bytes of output, according
    to the Posix manual."""

    def __init__(self, capture_fd=2):    # stderr by default
        if sys.platform == 'win32':
            import pytest
            pytest.skip("seems not to work, too bad")
        self.capture_fd = capture_fd

    def __enter__(self):
        import os
        self.read_fd, self.write_fd = os.pipe()
        self.copy_fd = os.dup(self.capture_fd)
        os.dup2(self.write_fd, self.capture_fd)
        return self

    def __exit__(self, *args):
        import os
        os.dup2(self.copy_fd, self.capture_fd)
        os.close(self.copy_fd)
        os.close(self.write_fd)
        self._value = os.read(self.read_fd, 512)
        os.close(self.read_fd)

    def getvalue(self):
        return self._value

def _verify(ffi, module_name, preamble, *args, **kwds):
    from cffi.recompiler import recompile
    from .udir import udir
    assert module_name not in sys.modules, "module name conflict: %r" % (
        module_name,)
    kwds.setdefault('tmpdir', str(udir))
    outputfilename = recompile(ffi, module_name, preamble, *args, **kwds)
    module = load_dynamic(module_name, outputfilename)
    #
    # hack hack hack: copy all *bound methods* from module.ffi back to the
    # ffi instance.  Then calls like ffi.new() will invoke module.ffi.new().
    for name in dir(module.ffi):
        if not name.startswith('_'):
            attr = getattr(module.ffi, name)
            if attr is not getattr(ffi, name, object()):
                setattr(ffi, name, attr)
    def typeof_disabled(*args, **kwds):
        raise NotImplementedError
    ffi._typeof = typeof_disabled
    for name in dir(ffi):
        if not name.startswith('_') and not hasattr(module.ffi, name):
            setattr(ffi, name, NotImplemented)
    return module.lib


# For testing, we call gcc with "-Werror".  This is fragile because newer
# versions of gcc are always better at producing warnings, particularly for
# auto-generated code.  We need here to adapt and silence them as needed.

if sys.platform == 'win32':
    extra_compile_args = []      # no obvious -Werror equivalent on MSVC
else:
    if (sys.platform == 'darwin' and
          [int(x) for x in os.uname()[2].split('.')] >= [11, 0, 0]):
        # assume a standard clang or gcc
        extra_compile_args = ['-Werror', '-Wall', '-Wextra', '-Wconversion',
                              '-Wno-unused-parameter',
                              '-Wno-unreachable-code']
        # special things for clang
        extra_compile_args.append('-Qunused-arguments')
    else:
        # assume a standard gcc
        extra_compile_args = ['-Werror', '-Wall', '-Wextra', '-Wconversion',
                              '-Wno-unused-parameter',
                              '-Wno-unreachable-code']

is_musl = False
if sys.platform == 'linux':
    try:
        from packaging.tags import platform_tags
    except ImportError:
        pass
    else:
        tagset = frozenset(platform_tags())
        is_musl = any(t.startswith('musllinux') for t in tagset)
        if is_musl and sys.version_info >= (3, 12):
            if any(t.startswith('musllinux_1_1_') for t in tagset) and not any(t.startswith('musllinux_1_2_') for t in tagset):
                # gcc 9.2.0 in the musllinux_1_1 build container has a bug in its sign-conversion warning detection that
                # bombs on the definition of _PyLong_CompactValue under Python 3.12; disable warnings-as-errors for that
                # specific error on musl 1.1
                extra_compile_args.append('-Wno-error=sign-conversion')

        del platform_tags
