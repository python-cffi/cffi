
from distutils.core import setup
import snip_package

setup(
    ext_package=['ext_package'],
    ext_modules=[snip_package.ffi.verifier.get_extension()])
