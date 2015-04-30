from setuptools import setup

setup(
    name="readdir2",
    version="0.1",
    py_modules=["readdir2"],
    setup_requires=["cffi>=1.0.dev0"],
    cffi_modules=[
        "readdir2_build:ffi",
    ],
    install_requires=["cffi>=1.0.dev0"],   # should maybe be "cffi-backend" only?
    zip_safe=False,
)
