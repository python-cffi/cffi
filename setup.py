import sys, os
from setuptools import setup, Feature, Extension


from setup_base import sources, libraries, include_dirs



setup(
    name='ffi',
    descripton='experimental ffi after the example of lua ffi',
    get_version_from_scm=True,

    url='https://bitbucket.org/cffi/cffi',
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
