import sys, os


from setup import include_dirs, sources, libraries


if __name__ == '__main__':
    from distutils.core import setup
    from distutils.extension import Extension
    setup(ext_modules=[Extension(name = '_ffi_backend',
                                 include_dirs=include_dirs,
                                 sources=sources,
                                 libraries=libraries,
                                 )])
