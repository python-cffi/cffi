import os
import pathlib
import pytest
import site
import subprocess
import sys
import sysconfig
import textwrap

from importlib.util import find_spec

if sys.platform == 'win32':
    pytestmark = pytest.mark.skip('snippets do not run on win32')

if sys.version_info < (2, 7):
    pytestmark = pytest.mark.skip(
                 'fails e.g. on a Debian/Ubuntu which patches virtualenv'
                 ' in a non-2.6-friendly way')

@pytest.fixture(scope="session")
def snippet_dir():
    return pathlib.Path(__file__).parent / 'snippets'

@pytest.fixture
def create_venv(tmp_path):
    venv_path = tmp_path / ".venv"

    def _create_venv(name):
        if find_spec("venv") is not None:
            venv_module = "venv"
            args = []
        else:
            venv_module = "virtualenv"
            args = ["--python", sys.executable]

        try:
            subprocess.check_call([sys.executable, "-m", venv_module, *args, str(venv_path)])

            # Python 3.12 venv/virtualenv no longer include setuptools and wheel by default, which
            # breaks a number of these tests; ensure it's always present for 3.12+
            if sys.version_info >= (3, 12):
                subprocess.check_call([
                    venv_path / "bin" / "python", "-m", "pip", "install", "--upgrade",
                    "setuptools",
                    "wheel",
                ])

        except OSError as e:
            pytest.skip("Cannot execute %s: %s" % (venv_module, e))

        site_packages = site.getsitepackages()
        paths = []
        if site_packages:
            if find_spec("cffi._pycparser") is not None:
                modules = ('cffi', '_cffi_backend')
            else:
                modules = ('cffi', '_cffi_backend', 'pycparser')
                if find_spec("ply") is not None:
                    modules += ('ply',)   # needed for older versions of pycparser

            paths = []
            for module in modules:
                target = __import__(module, None, None, [])
                if not hasattr(target, '__file__'):   # for _cffi_backend on pypy
                    continue

                src = os.path.abspath(target.__file__)
                for end in ['__init__.pyc', '__init__.pyo', '__init__.py']:
                    if src.lower().endswith(end):
                        src = src[:-len(end)-1]
                        break

                paths.append(os.path.dirname(src))

            paths = os.pathsep.join(paths)

        return venv_path, paths

    return _create_venv

@pytest.fixture
def setup_program(tmp_path_factory, snippet_dir):
    def _setup_program(dirname, venv_dir_and_paths, python_snippet):
        venv_dir, paths = venv_dir_and_paths
        olddir = os.getcwd()
        workdir = tmp_path_factory.mktemp("ffi-", numbered=True)
        python_file = workdir.joinpath('x.py')
        python_file.write_text(textwrap.dedent(python_snippet))
        try:
            os.chdir(str(snippet_dir.joinpath(dirname)))
            if os.name == 'nt':
                bindir = 'Scripts'
            else:
                bindir = 'bin'

            venv_python = str(venv_dir.joinpath(bindir).joinpath('python'))
            env = os.environ.copy()
            env['PYTHONPATH'] = paths
            subprocess.check_call((venv_python, 'setup.py', 'clean'), env=env)
            # there's a setuptools/easy_install bug that causes this to fail when the build/install occur together and
            # we're in the same directory with the build (it tries to look up dependencies for itself on PyPI);
            # subsequent runs will succeed because this test doesn't properly clean up the build- use pip for now.
            subprocess.check_call((venv_python, '-m', 'pip', 'install', '.'), env=env)
            subprocess.check_call((venv_python, str(python_file)), env=env)
        finally:
            os.chdir(olddir)

    return _setup_program

@pytest.fixture
def run_setup_and_program(tmp_path, create_venv, snippet_dir, setup_program):
    def _run_setup_and_program(dirname, python_snippet):
        venv_dir_and_paths = create_venv(dirname + '-cpy')
        setup_program(dirname, venv_dir_and_paths, python_snippet)

        sys._force_generic_engine_ = True
        try:
            venv_dir = create_venv(dirname + '-gen')
            setup_program(dirname, venv_dir, python_snippet)
        finally:
            del sys._force_generic_engine_

        # the two files lextab.py and yacctab.py are created by not-correctly-
        # installed versions of pycparser.
        assert not os.path.exists(str(snippet_dir.joinpath(dirname, 'lextab.py')))
        assert not os.path.exists(str(snippet_dir.joinpath(dirname, 'yacctab.py')))

    return _run_setup_and_program


def test_infrastructure(run_setup_and_program):
    run_setup_and_program('infrastructure', '''
    import snip_infrastructure
    assert snip_infrastructure.func() == 42
    ''')

def test_distutils_module(run_setup_and_program):
    run_setup_and_program("distutils_module", '''
    import snip_basic_verify
    p = snip_basic_verify.C.getpwuid(0)
    assert snip_basic_verify.ffi.string(p.pw_name) == b"root"
    ''')

def test_distutils_package_1(run_setup_and_program):
    run_setup_and_program("distutils_package_1", '''
    import snip_basic_verify1
    p = snip_basic_verify1.C.getpwuid(0)
    assert snip_basic_verify1.ffi.string(p.pw_name) == b"root"
    ''')

def test_distutils_package_2(run_setup_and_program):
    run_setup_and_program("distutils_package_2", '''
    import snip_basic_verify2
    p = snip_basic_verify2.C.getpwuid(0)
    assert snip_basic_verify2.ffi.string(p.pw_name) == b"root"
    ''')

def test_setuptools_module(run_setup_and_program):
    run_setup_and_program("setuptools_module", '''
    import snip_setuptools_verify
    p = snip_setuptools_verify.C.getpwuid(0)
    assert snip_setuptools_verify.ffi.string(p.pw_name) == b"root"
    ''')

def test_setuptools_package_1(run_setup_and_program):
    run_setup_and_program("setuptools_package_1", '''
    import snip_setuptools_verify1
    p = snip_setuptools_verify1.C.getpwuid(0)
    assert snip_setuptools_verify1.ffi.string(p.pw_name) == b"root"
    ''')

def test_setuptools_package_2(run_setup_and_program):
    run_setup_and_program("setuptools_package_2", '''
    import snip_setuptools_verify2
    p = snip_setuptools_verify2.C.getpwuid(0)
    assert snip_setuptools_verify2.ffi.string(p.pw_name) == b"root"
    ''')

def test_set_py_limited_api():
    from cffi.setuptools_ext import _set_py_limited_api
    try:
        import setuptools
    except ImportError as e:
        pytest.skip(str(e))
    orig_version = setuptools.__version__
        # free-threaded Python does not yet support limited API
    expecting_limited_api = not hasattr(sys, 'gettotalrefcount') and not sysconfig.get_config_var("Py_GIL_DISABLED")
    try:
        setuptools.__version__ = '26.0.0'
        from setuptools import Extension

        kwds = _set_py_limited_api(Extension, {})
        assert kwds.get('py_limited_api', False) == expecting_limited_api

        setuptools.__version__ = '25.0'
        kwds = _set_py_limited_api(Extension, {})
        assert kwds.get('py_limited_api', False) == False

        setuptools.__version__ = 'development'
        kwds = _set_py_limited_api(Extension, {})
        assert kwds.get('py_limited_api', False) == expecting_limited_api

    finally:
        setuptools.__version__ = orig_version
