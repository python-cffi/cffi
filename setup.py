import sys
from setuptools import setup, Feature, Extension

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
                          sources=['c/_ffi_backend.c']),
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
