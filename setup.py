import sys, os
from setuptools import setup, Feature, Extension


sources = ['c/_ffi_backend.c']
libraries = ['ffi']
include_dirs = []


if sys.platform == 'win32':
    COMPILE_LIBFFI = 'libffi_msvc'    # from the CPython distribution
else:
    COMPILE_LIBFFI = None

if COMPILE_LIBFFI:
    include_dirs.append(COMPILE_LIBFFI)
    libraries.remove('ffi')
    sources.extend(os.path.join(COMPILE_LIBFFI, filename)
                   for filename in os.listdir(COMPILE_LIBFFI)
                   if filename.lower().endswith('.c'))


setup(
    name='ffi',
    descripton='experimental ffi after the example of lua ffi',
    get_version_from_scm=True,

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
        'platformer',
        'pycparser',
    ]
)
