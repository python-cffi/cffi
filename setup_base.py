import sys, os


from setup import include_dirs, sources, libraries, define_macros


if __name__ == '__main__':
    from distutils.core import setup
    from distutils.extension import Extension
    setup(packages=['cffi'],
          ext_modules=[Extension(name = '_cffi_backend',
                                 include_dirs=include_dirs,
                                 sources=sources,
                                 libraries=libraries,
                                 define_macros=define_macros,
                                 )])
