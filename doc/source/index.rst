CFFI documentation
================================

.. toctree::
   :maxdepth: 2

Foreign Function Interface for Python calling C code. The aim of this project
is to provide a convenient and reliable way of calling C code from Python.
The interface is based on `luajit FFI`_ and follows a few principles:

* The goal is to call C code from Python.  You should be able to do so
  without learning a 3rd language: every alternative requires you to learn
  their own language (Cython_, SWIG_) or API (ctypes_).  So we tried to
  assume that you know Python and C and minimize the extra bits of API that
  you need to learn.

* Keep all the Python-related logic in Python so that you don't need to
  write much C code (unlike `CPython native C extensions`_).

* Work either at the level of the ABI (Application Binary Interface)
  or the API (Application Programming Interface).  Usually, C
  libraries have a specified C API but often not an ABI (e.g. they may
  document a "struct" as having at least these fields, but maybe more).
  (ctypes_ works at the ABI level, whereas `native C extensions`_
  work at the API level.)

* We try to be complete.  For now some C99 constructs are not supported,
  but all C89 should be, including macros (apart from the most advanced
  (ab)uses of these macros).

.. _`luajit FFI`: http://luajit.org/ext_ffi.html
.. _`Cython`: http://www.cython.org
.. _`SWIG`: http://www.swig.org/
.. _`CPython native C extensions`: http://docs.python.org/extending/extending.html
.. _`native C extensions`: http://docs.python.org/extending/extending.html
.. _`ctypes`: http://docs.python.org/library/ctypes.html


Simple example (ABI level)
--------------------------

.. code-block:: python

    >>> from cffi import FFI
    >>> ffi = FFI()
    >>> ffi.cdef("""
    ...     int printf(const char *format, ...);   // copy-pasted from the man page
    ... """)                                  
    >>> C = ffi.dlopen(None)                     # loads the entire C namespace
    >>> arg = ffi.new("char[]", "world")         # equivalent to C code: char arg[] = "world";
    >>> C.printf("hi there, %s!\n", arg);        # call printf
    hi there, world!


Real example (API level)
------------------------

.. code-block:: python

    from cffi import FFI
    ffi = FFI()
    ffi.cdef("""     // some declarations from the man page
        struct passwd {
            char *pw_name;
            ...;
        };
        struct passwd *getpwuid(int uid);
    """)
    C = ffi.verify("""   // passed to the real C compiler
    #include <sys/types.h>
    #include <pwd.h>
    """)
    assert str(C.getpwuid(0).pw_name) == 'root'

Note that the above example works independently of the exact layout of
``struct passwd``, but so far require a C compiler at runtime.  (We plan
to improve with caching and a way to distribute the compiled code.)

Struct/Array Example
--------------------

.. code-block:: python

    from cffi import FFI
    ffi = FFI()
    ffi.cdef("""
        typedef struct {
            unsigned char r, g, b;
        } pixel_t;
    """)
    image = ffi.new("pixel_t[]", 800*600)
    image[0].r = 255
    image[0].g = 192
    image[0].b = 128

This can be used as a more flexible replacement of the struct_ and
array_ modules.  You could also call ``ffi.new("pixel_t[600][800]")``
and get a two-dimensional array.

.. _struct: http://docs.python.org/library/struct.html
.. _array: http://docs.python.org/library/array.html


What has actually happened?
---------------------------

CFFI interface operates on the same level as C - you declare types and functions
pretty much the same way you would define them in C. In fact most of the examples
from manpages can be copied without changes.

The declarations can contain types, functions and global variables.
The cdef in the above example is just that -
it declared "there is a function in the C level with a given signature".

The next line loads libraries. C has multiple namespaces - a global one and local
ones per library. In this example we load the global one (None as argument to dlopen)
which always contains the standard C library.

Next line is allocating new char[] object and then calling the printf. Simple, isn't it?

Declaring types and functions
-----------------------------

There is not much to say here

Loading libraries
-----------------

Working with pointers, structures and arrays
--------------------------------------------

The verification step
---------------------

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

