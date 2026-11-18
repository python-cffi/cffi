
import snip_setuptools_verify
from setuptools import setup

setup(
    zip_safe=False,
    py_modules=['snip_setuptools_verify'],
    ext_modules=[snip_setuptools_verify.ffi.verifier.get_extension()])
