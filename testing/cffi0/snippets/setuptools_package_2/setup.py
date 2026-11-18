
import snip_setuptools_verify2
from setuptools import setup

setup(
    zip_safe=False,
    packages=['snip_setuptools_verify2'],
    ext_package='snip_setuptools_verify2',
    ext_modules=[snip_setuptools_verify2.ffi.verifier.get_extension()])
