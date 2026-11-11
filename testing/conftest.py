import os
import pytest
import sys

from ctypes import util

try:
    import pytest_run_parallel  # noqa:F401
    PARALLEL_RUN_AVAILABLE = True
except Exception:
    PARALLEL_RUN_AVAILABLE = False

def _msvc_env():
    """Query the MSVC environment for the platform we are running on."""
    from setuptools._distutils.util import get_platform
    try:
        # setuptools >= 80
        from setuptools._distutils.compilers.C.msvc import (
            _get_vc_env, _get_vcvars_spec)
        from setuptools._distutils.util import get_host_platform
        spec = _get_vcvars_spec(get_host_platform(), get_platform())
    except ImportError:
        from setuptools._distutils._msvccompiler import (
            _get_vc_env, PLAT_TO_VCVARS)
        spec = PLAT_TO_VCVARS[get_platform()]
    return _get_vc_env(spec)


def _prime_msvc_env():
    """Put the MSVC environment in os.environ once, on windows.

    _get_vc_env() runs 'cmd /u /c vcvarsall.bat && set' and caches nothing,
    and it is called from MSVCCompiler.initialize(), i.e. once per compiler
    instance.  cffi builds a fresh compiler for every ffi.verify(), so this
    suite would spawn vcvarsall hundreds of times.  Querying it once and
    setting DISTUTILS_USE_SDK makes _get_vc_env() return os.environ instead.

    It also puts cl.exe on PATH, which is where meson looks for a compiler
    before falling back to a stray mingw gcc.
    """
    if sys.platform != 'win32' or os.environ.get('DISTUTILS_USE_SDK'):
        return
    try:
        env = _msvc_env()
    except Exception:
        return          # leave distutils to find the compiler by itself
    # vcvarsall inherits our environment, so these already include whatever
    # PATH/INCLUDE/LIB we were started with
    wanted = {key: env.get(key.lower(), '')
              for key in ('PATH', 'INCLUDE', 'LIB', 'LIBPATH')}
    if not all(wanted[key] for key in ('PATH', 'INCLUDE', 'LIB')):
        return
    os.environ.update(wanted)
    os.environ['DISTUTILS_USE_SDK'] = '1'


def pytest_configure(config):
    _prime_msvc_env()
    # Don't warn for `pytest-run-parallel` markers if they're not available
    if not PARALLEL_RUN_AVAILABLE:
        config.addinivalue_line(
            'markers',
            'parallel_threads(n): run the given test function in parallel '
            'using `n` threads.')
        config.addinivalue_line(
            "markers",
            "thread_unsafe: mark the test function as single-threaded",
        )
        config.addinivalue_line(
            "markers",
            "iterations(n): run the given test function `n` times in each thread",
        )

try:
    gil_enabled_at_start = sys._is_gil_enabled()
except AttributeError:
    # Python 3.12 and older
    gil_enabled_at_start = True

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not gil_enabled_at_start and sys._is_gil_enabled():
        tr = terminalreporter
        tr.ensure_newline()
        tr.section("GIL re-enabled!", sep="=", red=True, bold=True)
        tr.line("The GIL was re-enabled at runtime during the tests.")
        tr.line("Re-run the test with '-W error::RuntimeWarning' to ")
        tr.line("make the tests fail when the GIL is re-enabled.")
        pytest.exit("GIL re-enabled during tests", returncode=1)


# this problem was supposedly fixed in a newer Python 3.8 release, but after binary installer support expired
# https://github.com/python/cpython/pull/28054
if sys.platform == 'darwin' and sys.version_info[:2] == (3, 8):
    orig_find_library = util.find_library

    def hacked_find_library(*args, **kwargs):
        res = orig_find_library(*args, **kwargs)

        if res is None:
            pytest.xfail("busted find_library on MacOS Python 3.8")

        return res

    util.find_library = hacked_find_library
