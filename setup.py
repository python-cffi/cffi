import sys, os
import subprocess
import errno


sources = ['c/_cffi_backend.c']
libraries = ['ffi']
include_dirs = ['/usr/include/ffi',
                '/usr/include/libffi']    # may be changed by pkg-config
define_macros = []
library_dirs = []
extra_compile_args = []
extra_link_args = []


def _ask_pkg_config(resultlist, option, result_prefix=''):
    try:
        p = subprocess.Popen(['pkg-config', option, 'libffi'],
                             stdout=subprocess.PIPE, stderr=open('/dev/null', 'w'))
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    else:
        t = p.stdout.read().decode().strip()
        if p.wait() == 0:
            res = t.split()
            # '-I/usr/...' -> '/usr/...'
            for x in res:
                assert x.startswith(result_prefix)
            res = [x[len(result_prefix):] for x in res]
            #print 'PKG_CONFIG:', option, res
            resultlist[:] = res

def use_pkg_config():
    _ask_pkg_config(include_dirs,       '--cflags-only-I', '-I')
    _ask_pkg_config(extra_compile_args, '--cflags-only-other')
    _ask_pkg_config(library_dirs,       '--libs-only-L', '-L')
    _ask_pkg_config(extra_link_args,    '--libs-only-other')
    _ask_pkg_config(libraries,          '--libs-only-l', '-l')


if sys.platform == 'win32':
    COMPILE_LIBFFI = 'c/libffi_msvc'    # from the CPython distribution
else:
    COMPILE_LIBFFI = None

if COMPILE_LIBFFI:
    assert os.path.isdir(COMPILE_LIBFFI), (
        "On Windows, you need to copy the directory "
        "Modules\\_ctypes\\libffi_msvc from the CPython sources (2.6 or 2.7) "
        "into the top-level directory.")
    include_dirs[:] = [COMPILE_LIBFFI]
    libraries[:] = []
    _filenames = [filename.lower() for filename in os.listdir(COMPILE_LIBFFI)]
    _filenames = [filename for filename in _filenames
                           if filename.endswith('.c') or
                              filename.endswith('.asm')]
    if sys.maxsize <= 2**32:
        _filenames.remove('win64.asm')
    else:
        _filenames.remove('win32.c')
    sources.extend(os.path.join(COMPILE_LIBFFI, filename)
                   for filename in _filenames)
    define_macros.append(('USE_C_LIBFFI_MSVC', '1'))
else:
    use_pkg_config()


if __name__ == '__main__':
  from setuptools import setup, Feature, Extension
  setup(
    name='cffi',
    description='Foreign Function Interface for Python calling C code.',
    version='0.3',
    packages=['cffi'],

    url='http://cffi.readthedocs.org',
    author='Armin Rigo, Maciej Fijalkowski',
    author_email='python-cffi@googlegroups.com',

    license='MIT',

    features={
        'cextension': Feature(
            "fast c backend for cpython",
            standard='__pypy__' not in sys.modules,
            ext_modules=[
                Extension(name='_cffi_backend',
                          include_dirs=include_dirs,
                          sources=sources,
                          libraries=libraries,
                          define_macros=define_macros),
            ],
        ),
    },

    setup_requires=[
        'hgdistver',
    ],
    install_requires=[
        # pycparser 2.08 no longer contains lextab.py/yacctab.py
        # out of the box, which looks like a bug
        'pycparser<=2.07',
    ]
  )
