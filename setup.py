import sys, os
import subprocess
import errno


sources = ['c/_cffi_backend.c']
libraries = ['ffi']
include_dirs = []
define_macros = []


if sys.platform == 'win32':
    COMPILE_LIBFFI = 'c/libffi_msvc'    # from the CPython distribution
else:
    COMPILE_LIBFFI = None

if COMPILE_LIBFFI:
    assert os.path.isdir(COMPILE_LIBFFI), (
        "On Windows, you need to copy the directory "
        "Modules\\_ctypes\\libffi_msvc from the CPython sources (2.6 or 2.7) "
        "into the top-level directory.")
    include_dirs.append(COMPILE_LIBFFI)
    libraries.remove('ffi')
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
    try:
        p = subprocess.Popen(['pkg-config', '--cflags-only-I', 'libffi'],
                             stdout=subprocess.PIPE, stderr=open('/dev/null', 'w'))
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise
    else:
        t = p.stdout.read().strip()
        if p.wait() == 0 and t:
            # '-I/usr/...' -> '/usr/...'
            include_dirs.append(t[2:])


if __name__ == '__main__':
  from setuptools import setup, Feature, Extension
  setup(
    name='cffi',
    description='Foreign Function Interface for Python calling C code.',
    get_version_from_scm=True,
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
        'pycparser',
    ]
  )
