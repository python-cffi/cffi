from setuptools import setup

setup(
    name="_curses",
    version="0.1",
    py_modules=["_curses"],
    setup_requires=["cffi>=1.0"],
    cffi_modules=[
        "_curses_build:ffi",
    ],
    install_requires=["cffi>=1.0"],   # should maybe be "cffi-backend" only?
    zip_safe=False,
)
