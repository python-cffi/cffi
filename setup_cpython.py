from distutils.core import setup
from distutils.extension import Extension

setup(name        = "ffi",
      version     = "0.1",
      description = 'experimental ffi after the example of lua ffi',
      ext_modules = [Extension(name = '_ffi_backend',
                               sources = ['c/_ffi_backend.c'])]
      )
