cffi
====

Foreign Function Interface for Python calling C code. The aim of this project
is to provide a convinient and reliable way of calling C code from Python.
The interface is based on [luajit FFI](http://luajit.org/ext_ffi.html) and follows a few principles:

* You want to use C code from Python code, so you should be able to do so
  without needing to learn a 3rd language
  (unlike [Cython](http://www.cython.org) or [SWIG](http://www.swig.org/) or ctypes)

* Keep all the python-related logic in Python instead of C (unlike
  [CPython native C extensions](http://docs.python.org/extending/extending.html))

* Be complete and work on the level of API (unlike [ctypes](http://docs.python.org/library/ctypes.html))

Simple example
--------------

    >>> from cffi import FFI
    >>> ffi = FFI()
    >>> ffi.cdef("""
    ...     int printf(const char *format, ...); // copy-pasted from the man page
    ... """)                                  
    >>> C = ffi.dlopen(None)                     # loads the entire C namespace
    >>> arg = ffi.new("char[]", "world")         # equivalent to C code: char arg[] = "world";
    >>> C.printf("hi there, %s!\n", arg);        # call printf
    hi there, world!
    >>>

More documentation
------------------

See [More docs](https://bitbucket.org/xxx) for examples and supported features.

Contact
-------

[Mailing list](https://groups.google.com/forum/#!forum/python-cffi)


Initial motivation
------------------

http://mail.python.org/pipermail/pypy-dev/2012-May/009915.html
