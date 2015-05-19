=======================================================
Overview
=======================================================

CFFI can be used in one of four modes: "ABI" versus "API" level,
each with "in-line" or "out-of-line" preparation (or compilation).

The **ABI mode** accesses libraries at the binary level, whereas the
**API mode** accesses them with a C compiler.  This is described in
detail below__.

.. __: `abi-versus-api`_

In the **in-line mode,** everything is set up every time you import
your Python code.  In the **out-of-line mode,** you have a separate
step of preparation (and possibly C compilation) that produces a
module which your main program can then import.

(The examples below assume that you have `installed CFFI`__.)

.. __: installation.html


Simple example (ABI level, in-line)
-----------------------------------

.. code-block:: python

    >>> from cffi import FFI
    >>> ffi = FFI()
    >>> ffi.cdef("""
    ...     int printf(const char *format, ...);   // copy-pasted from the man page
    ... """)                                  
    >>> C = ffi.dlopen(None)                     # loads the entire C namespace
    >>> arg = ffi.new("char[]", "world")         # equivalent to C code: char arg[] = "world";
    >>> C.printf("hi there, %s!\n", arg)         # call printf
    hi there, world!

Note that on Python 3 you need to pass byte strings to ``char *``
arguments.  In the above example it would be ``b"world"`` and ``b"hi
there, %s!\n"``.  In general it is ``somestring.encode(myencoding)``.


.. _out-of-line-abi-level:

Out-of-line example (ABI level, out-of-line)
--------------------------------------------

In a real program, you would not include the ``ffi.cdef()`` in your
main program's modules.  Instead, you can rewrite it as follows.  It
massively reduces the import times, because it is slow to parse a
large C header.  It also allows you to do more detailed checkings
during build-time without worrying about performance (e.g. calling
``cdef()`` many times with small pieces of declarations, based
on the version of libraries detected on the system).

.. code-block:: python

    # file "simple_example_build.py"

    from cffi import FFI

    ffi = FFI()
    ffi.set_source("_simple_example", None)
    ffi.cdef("""
        int printf(const char *format, ...);
    """)

    if __name__ == "__main__":
        ffi.compile()

Running it once produces ``_simple_example.py``.  Your main program
only imports this generated module, not ``simple_example_build.py``
any more:

.. code-block:: python

    from _simple_example import ffi

    lib = ffi.dlopen(None)         # or path to a library
    lib.printf(b"hi there, number %d\n", ffi.cast("int", 2))

For distribution purposes, remember that there is a new
``_simple_example.py`` file generated.  You can either include it
statically within your project's source files, or, with Setuptools,
you can say in the ``setup.py``:

.. code-block:: python

    from setuptools import setup

    setup(
        ...
        setup_requires=["cffi>=1.0.0"],
        cffi_modules=["simple_example_build.py:ffi"],
        install_requires=["cffi>=1.0.0"],
    )


.. _out-of-line-api-level:
.. _real-example:

Real example (API level, out-of-line)
-------------------------------------

.. code-block:: python

    # file "example_build.py"

    from cffi import FFI
    ffi = FFI()

    ffi.set_source("_example",
        """ // passed to the real C compiler
            #include <sys/types.h>
            #include <pwd.h>
        """,
        libraries=[])   # or a list of libraries to link with

   ffi.cdef("""     // some declarations from the man page
        struct passwd {
            char *pw_name;
            ...;     // literally dot-dot-dot
        };
        struct passwd *getpwuid(int uid);
    """)

    if __name__ == "__main__":
        ffi.compile()

You need to run the ``example_build.py`` script once to generate
"source code" into the file ``_example.c`` and compile this to a
regular C extension module.  (CFFI selects either Python or C for the
module to generate based on whether the second argument to
``set_source()`` is ``None`` or not.)

Then, in your main program, you use:

.. code-block:: python

    from _example import ffi, lib

    p = lib.getpwuid(0)
    assert ffi.string(p.pw_name) == b'root'

Note that this works independently of the exact C layout of ``struct
passwd`` (it is "API level", as opposed to "ABI level").  It requires
a C compiler in order to run ``example_build.py``, but it is much more
portable than trying to get the details of the fields of ``struct
passwd`` exactly right.  Similarly, we declared ``getpwuid()`` as
taking an ``int`` argument.  On some platforms this might be slightly
incorrect---but it does not matter.

To integrate it inside a ``setup.py`` distribution with Setuptools:

.. code-block:: python

    from setuptools import setup

    setup(
        ...
        setup_requires=["cffi>=1.0.0"],
        cffi_modules=["example_build.py:ffi"],
        install_requires=["cffi>=1.0.0"],
    )

Struct/Array Example (minimal, in-line)
---------------------------------------

.. code-block:: python

    from cffi import FFI
    ffi = FFI()
    ffi.cdef("""
        typedef struct {
            unsigned char r, g, b;
        } pixel_t;
    """)
    image = ffi.new("pixel_t[]", 800*600)

    f = open('data', 'rb')     # binary mode -- important
    f.readinto(ffi.buffer(image))
    f.close()

    image[100].r = 255
    image[100].g = 192
    image[100].b = 128

    f = open('data', 'wb')
    f.write(ffi.buffer(image))
    f.close()

This can be used as a more flexible replacement of the struct_ and
array_ modules.  You could also call ``ffi.new("pixel_t[600][800]")``
and get a two-dimensional array.

.. _struct: http://docs.python.org/library/struct.html
.. _array: http://docs.python.org/library/array.html


What actually happened?
-----------------------

The CFFI interface operates on the same level as C - you declare types
and functions using the same syntax as you would define them in C.  This
means that most of the documentation or examples can be copied straight
from the man pages.

The declarations can contain **types, functions, constants**
and **global variables.** What you pass to the ``cdef()`` must not
contain more than that; in particular, ``#ifdef`` or ``#include``
directives are not supported.  The cdef in the above examples are just
that - they declared "there is a function in the C level with this
given signature", or "there is a struct type with this shape".

In the ABI examples, the ``dlopen()`` calls load libraries manually.
At the binary level, a program is split into multiple namespaces---a
global one (on some platforms), plus one namespace per library.  So
``dlopen()`` returns a ``<FFILibrary>`` object, and this object has
got as attributes all function, constant and variable symbols that are
coming from this library and that have been declared in the
``cdef()``.

By opposition, the API examples work like a C program does: the C
linker (static or dynamic) is responsible for finding any symbol used.
You name the libraries in the ``libraries`` keyword argument to
``set_source()``.  Other common arguments include ``library_dirs`` and
``include_dirs``; all these arguments are passed to the standard
distutils/setuptools.

The ``ffi.new()`` lines allocate C objects.  They are filled
with zeroes initially, unless the optional second argument is used.
If specified, this argument gives an "initializer", like you can use
with C code to initialize global variables.

The actual ``lib.*()`` function calls should be obvious: it's like C.


.. _abi-versus-api:

ABI versus API
--------------

Accessing the C library at the binary level ("ABI") is fraught
with problems, particularly on non-Windows platforms.  You are not
meant to access fields by guessing where they are in the structures.
*The C libraries are typically meant to be used with a C compiler.*

The second example shows how to do that: instead of doing a ``dlopen()``,
we use ``set_source(..., "C header...")``.  When using this approach
we have the advantage that we can use "``...``" at various places in
the ``cdef()``, and the missing information will be completed with the
help of the C compiler.  Actually, a single C source file is produced,
which contains first the ``C header`` part unmodified, followed by
"magic" C code and declarations derived from the ``cdef()``.  When
this C file is compiled, the resulting C extension module will contain
all the information we need---or the C compiler will give warnings or
errors, as usual e.g. if you misdeclare some function's signature.

Note that the ``C header`` part can contain arbitrary C code.  You can
use it to declare some more helpers written in C.  To export these
helpers to Python, put their signature in the ``cdef()`` too.  This
can be used for example to wrap "crazy" macros into more standard C
functions.  (If all you need is to call "non-crazy" macros, then you
can directly declare them in the ``cdef()`` as if they were
functions.)

The generated piece of C code should be the same independently on the
platform on which you run it, so in simple cases you can simply
distribute the pre-generated C code and treat it as a regular C
extension module.  The special Setuptools lines in the `example
above`__ are meant for the more complicated cases where we need to
regenerate the C sources as well---e.g. because the Python script that
regenerates this file will itself look around the system to know what
it should include or not.

.. __: real-example_

Note that the "API level + in-line" mode combination is deprecated.
It used to be done with ``lib = ffi.verify("C header")``.  The
out-of-line variant with ``set_source("modname", "C header")`` is
preferred.
