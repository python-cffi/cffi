from setuptools import setup

setup(
    name='ffi',
    descripton='experimental ffi after the example of lua ffi',
    get_version_from_scm=True,

    setup_requires=[
        'hgdistver',
    ],
)


