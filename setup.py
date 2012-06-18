import sys, os


sources = ['c/_ffi_backend.c']
libraries = ['ffi']
include_dirs = []


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
    sources.extend(os.path.join(COMPILE_LIBFFI, filename)
                   for filename in os.listdir(COMPILE_LIBFFI)
                   if filename.lower().endswith('.c'))


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

    features={
        'cextension': Feature(
            "fast c backend for cpython",
            standard='__pypy__' not in sys.modules,
            ext_modules=[
                Extension(name='_ffi_backend',
                          include_dirs=include_dirs,
                          sources=sources,
                          libraries=libraries),
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
