
from setuptools import setup
import snip_setuptools_verify

setup(
    zip_safe=False,
    packages=['snip_setuptools_verify'],
    ext_modules=[snip_setuptools_verify.ffi.verifier.get_extension()])
