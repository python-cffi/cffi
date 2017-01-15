CFFI
====

Foreign Function Interface for Python calling C code.
Please see the [Documentation](http://cffi.readthedocs.org/) or uncompiled
in the doc/ subdirectory.

Download
--------

[Download page](https://bitbucket.org/cffi/cffi/downloads)

Contact
-------

[Mailing list](https://groups.google.com/forum/#!forum/python-cffi)

Testing/development tips
------------------------

To run tests under CPython, run::

    pip install pytest     # if you don't have py.test already
    python setup.py build_ext -f -i
    py.test c/ test/

If you run in another directory (either the tests or another program),
you should use the environment variable ``PYTHONPATH=/path`` to point
to the location that contains the ``_cffi_backend.so`` just compiled.
