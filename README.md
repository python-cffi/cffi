CFFI
====

Foreign Function Interface for Python calling C code. The aim of this project
is to provide a convenient and reliable way of calling C code from Python.
The interface is based on [luajit FFI](http://luajit.org/ext_ffi.html) and
follows a few principles:

* The goal is to call C code from Python.  You should be able to do so
  without learning a 3rd language: every alternative requires you to learn
  their own language ([Cython](http://www.cython.org),
  [SWIG](http://www.swig.org/)) or API
  ([ctypes](http://docs.python.org/library/ctypes.html)).  So we tried to
  assume that you know Python and C and minimize the extra bits of API that
  you need to learn.

* Keep all the Python-related logic in Python so that you don't need to
  write much C code (unlike
  [CPython native C extensions](http://docs.python.org/extending/extending.html)).

* Work either at the level of the ABI (Application Binary Interface)
  or the API (Application Programming Interface).  Usually, C
  libraries have a specified C API but often not an ABI (e.g. they may
  document a "struct" as having at least these fields, but maybe more).
  ([ctypes](http://docs.python.org/library/ctypes.html) works at the ABI
  level, whereas
  [native C extensions](http://docs.python.org/extending/extending.html)
  work at the API level.)

* We try to be complete.  For now some C99 constructs are not supported,
  but all C89 should be, including macros (apart from the most advanced
  (ab)uses of these macros).

Simple example (ABI level)
--------------------------

    >>> from cffi import FFI
    >>> ffi = FFI()
    >>> ffi.cdef("""
    ...     int printf(const char *format, ...);     // copy-pasted from the man page
    ... """)                                  
    >>> C = ffi.dlopen(None)                     # loads the entire C namespace
    >>> arg = ffi.new("char[]", "world")         # equivalent to C code: char arg[] = "world";
    >>> C.printf("hi there, %s!\n", arg);        # call printf
    hi there, world!
    >>>

Real example (API level)
------------------------

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
"struct passwd", but so far require a C compiler at runtime.  (We plan
to improve with caching and a way to distribute the compiled code.)

Struct/Array Example
--------------------

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

This can be used as a more flexible replacement of the
[struct](http://docs.python.org/library/struct.html) and
[array](http://docs.python.org/library/array.html) modules.
You could also call ``ffi.new("pixel_t[600][800]")``
and get a two-dimensional array.


More documentation
------------------

See [More docs](http://cffi.readthedocs.org/) for examples and supported features.

Contact
-------

[Mailing list](https://groups.google.com/forum/#!forum/python-cffi)


Initial motivation
------------------

http://mail.python.org/pipermail/pypy-dev/2012-May/009915.html
