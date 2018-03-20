=======================================================
Overview
=======================================================

.. contents::
   

This document starts, in the first section, with a simple working
example of using CFFI to call a C function from Python. CFFI is
flexible and covers several use cases presented in the second
section. Then, the next section shows how to export Python functions
to a Python interpreter embedded in a C or C++ application. The last
two sections delve deeper in the CFFI library.

Make sure you have `cffi installed`__.

.. __: installation.html

.. _out-of-line-api-level:
.. _real-example:


Example: calling a C function from Python
-----------------------------------------

This example is about the use case when the library sources are
available, the next section shows how use a compiled, installed
library.

1. Make sure the sources of the library defining the useful C function
   is available. For this example, create the file ``pi.c`` and ``pi.h``:

   .. code-block:: C

      /* filename: pi.c*/
      # include <stdlib.h>
      # include <math.h>
       
      /* Returns a very crude approximation of Pi
         given a int: a number of iteration */
      float pi_approx(int n){
      
        double i,x,y,sum=0;
      
        for(i=0;i<n;i++){
      
          x=rand();
          y=rand();
      
          if (sqrt(x*x+y*y) < sqrt((double)RAND_MAX*RAND_MAX))
            sum++; }
      
        return 4*(float)sum/(float)n; }

   .. code-block:: C

      /* filename: pi.h*/
      float pi_approx(int n);
      
2. Create a script named ``pi_extension_build.py``, building
   the C extension:
   
   .. code-block:: python

      from cffi import FFI
      ffibuilder = FFI()
      
      # cdef() expects a string listing the C types, functions and 
      # globals needed from Python. The string is in the C syntax,
      # which saves us from learning a Python descriptive dialect.
      ffibuilder.cdef("float pi_approx(int n);")
   
      ffibuilder.set_source(       
          "_pi",  # name of the output C extension
      	   '# include "pi.h"',
      	   sources=['pi.c'],
      	   libraries=['m'])
   
      if __name__ == "__main__":
          ffibuilder.compile(verbose=True)

       
3. Build the extension:
   
   .. code-block:: shell

      python pi_extension_build.py

   Observe, in the working directory, the generated output files:
   ``_pi.c``, ``_pi.o`` and the C extension ``_pi.so``.


4. Call the C function from Python:

   .. code-block:: python
   
       from _pi.lib import pi_approx
   
       approx = pi_approx(10)
       assert str(pi_approximation).startswith("3.")
   
       approx = pi_approx(10000)
       assert str(approx).startswith("3.1")  

For more information, see the ``cdef()`` and ``set_source()`` methods
of the ``FFI`` class covered in `Preparing and Distributing modules`__.

.. __: cdef.html


A common alternative for the step 3. and running the build script is
to write a ``setup.py`` Setuptools distribution:

.. code-block:: python

    from setuptools import setup

    setup(
        ...
        setup_requires=["cffi>=1.0.0"],
        cffi_modules=["pi_extension_build:ffibuilder"],
        install_requires=["cffi>=1.0.0"],
    )

``cffi_modules`` is a list of ``<extension builder script>:<FFI
instance>`` describing the modules to build.


Other CFFI modes
----------------

CFFI can be used in one of four modes: "ABI" versus "API" level,
each with "in-line" or "out-of-line" preparation (or compilation).

The **ABI mode** accesses libraries at the binary level, whereas the
faster **API mode** accesses them with a C compiler.  This is described in
detail below__.

.. __: `abi-versus-api`_

In the **in-line mode,** everything is set up every time you import
your Python code.  In the **out-of-line mode,** you have a separate
step of preparation (and possibly C compilation) that produces a
module which your main program can then import.


Simple example (ABI level, in-line)
+++++++++++++++++++++++++++++++++++

.. code-block:: python

    >>> from cffi import FFI
    >>> ffi = FFI()
    >>> ffi.cdef("""
    ...     int printf(const char *format, ...);   // copy-pasted from the man page
    ... """)                                  
    >>> C = ffi.dlopen(None)                     # loads the entire C namespace
    >>> arg = ffi.new("char[]", "world")         # equivalent to C code: char arg[] = "world";
    >>> C.printf("hi there, %s.\n", arg)         # call printf
    hi there, world.
    17                                           # this is the return value
    >>>

Note that on Python 3 you need to pass byte strings to ``char *``
arguments.  In the above example it would be ``b"world"`` and ``b"hi
there, %s!\n"``.  In general it is ``somestring.encode(myencoding)``.

*Python 3 on Windows:* ``ffi.dlopen(None)`` does not work.  This problem
is messy and not really fixable.  The problem does not occur if you try
to call a fucntion from a specific DLL that exists on your system: then
you use ``ffi.dlopen("path.dll")``.

*This example does not call any C compiler.  It works in the so-called
ABI mode, which means that it will crash if you call some function or
access some fields of a structure that was slightly misdeclared in the
cdef().*

If using a C compiler to install your module is an option, it is highly
recommended to use the API mode described in the next paragraph.  (It is
also faster.)



Struct/Array Example (minimal, in-line)
+++++++++++++++++++++++++++++++++++++++

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

*This example does not call any C compiler.*

This example also admits an out-of-line equivalent.  It is similar to
the first example `Example: calling a C function from Python`_ above,
but passing ``None`` as the second argument to
``ffibuilder.set_source()``.  Then in the main program you write
``from _simple_example import ffi`` and then the same content as the
in-line example above starting from the line ``image =
ffi.new("pixel_t[]", 800*600)``.


.. _performance:

Purely for performance (API level, out-of-line)
+++++++++++++++++++++++++++++++++++++++++++++++

A variant of the `section above`__ where the goal is not to call an
existing C library, but to compile and call some C function written
directly in the build script:

.. __: real-example_

.. code-block:: python

    # file "example_build.py"

    from cffi import FFI
    ffibuilder = FFI()

    ffibuilder.cdef("int foo(int *, int *, int);")

    ffibuilder.set_source("_example",
    r"""
        static int foo(int *buffer_in, int *buffer_out, int x)
        {
            /* some algorithm that is seriously faster in C than in Python */
        }
    """)

    if __name__ == "__main__":
        ffibuilder.compile(verbose=True)

.. code-block:: python

    # file "example.py"

    from _example import ffi, lib

    buffer_in = ffi.new("int[]", 1000)
    # initialize buffer_in here...

    # easier to do all buffer allocations in Python and pass them to C,
    # even for output-only arguments
    buffer_out = ffi.new("int[]", 1000)

    result = lib.foo(buffer_in, buffer_out, 1000)

*You need a C compiler to run example_build.py, once.  It produces a
file called e.g. _example.so or _example.pyd.  If needed, it can be
distributed in precompiled form like any other extension module.*


.. _out-of-line-abi-level:

Out-of-line, ABI level
++++++++++++++++++++++

The out-of-line ABI mode is a mixture of the regular (API) out-of-line
mode and the in-line ABI mode.  It lets you use the ABI mode, with its
advantages (not requiring a C compiler) and problems (crashes more
easily).

This mixture mode lets you massively reduces the import times, because
it is slow to parse a large C header.  It also allows you to do more
detailed checkings during build-time without worrying about performance
(e.g. calling ``cdef()`` many times with small pieces of declarations,
based on the version of libraries detected on the system).

.. code-block:: python

    # file "simple_example_build.py"

    from cffi import FFI

    ffibuilder = FFI()
    ffibuilder.set_source("_simple_example", None)
    ffibuilder.cdef("""
        int printf(const char *format, ...);
    """)

    if __name__ == "__main__":
        ffibuilder.compile(verbose=True)

Running it once produces ``_simple_example.py``.  Your main program
only imports this generated module, not ``simple_example_build.py``
any more:

.. code-block:: python

    from _simple_example import ffi

    lib = ffi.dlopen(None)      # Unix: open the standard C library
    #import ctypes.util         # or, try this on Windows:
    #lib = ffi.dlopen(ctypes.util.find_library("c"))

    lib.printf(b"hi there, number %d\n", ffi.cast("int", 2))

Note that this ``ffi.dlopen()``, unlike the one from in-line mode,
does not invoke any additional magic to locate the library: it must be
a path name (with or without a directory), as required by the C
``dlopen()`` or ``LoadLibrary()`` functions.  This means that
``ffi.dlopen("libfoo.so")`` is ok, but ``ffi.dlopen("foo")`` is not.
In the latter case, you could replace it with
``ffi.dlopen(ctypes.util.find_library("foo"))``.  Also, None is only
recognized on Unix to open the standard C library.

For distribution purposes, remember that there is a new
``_simple_example.py`` file generated.  You can either include it
statically within your project's source files, or, with Setuptools,
you can say in the ``setup.py``:

.. code-block:: python

    from setuptools import setup

    setup(
        ...
        setup_requires=["cffi>=1.0.0"],
        cffi_modules=["simple_example_build.py:ffibuilder"],
        install_requires=["cffi>=1.0.0"],
    )


.. _embedding:

Embedding
---------

*New in version 1.5.*

CFFI can be used for embedding__: creating a standard
dynamically-linked library (``.dll`` under Windows, ``.so`` elsewhere)
which can be used from a C application.

.. code-block:: python

    import cffi
    ffibuilder = cffi.FFI()

    ffibuilder.embedding_api("""
        int do_stuff(int, int);
    """)

    ffibuilder.set_source("my_plugin", "")

    ffibuilder.embedding_init_code("""
        from my_plugin import ffi

        @ffi.def_extern()
        def do_stuff(x, y):
            print("adding %d and %d" % (x, y))
            return x + y
    """)

    ffibuilder.compile(target="plugin-1.5.*", verbose=True)

This simple example creates ``plugin-1.5.dll`` or ``plugin-1.5.so`` as
a DLL with a single exported function, ``do_stuff()``.  You execute
the script above once, with the interpreter you want to have
internally used; it can be CPython 2.x or 3.x or PyPy.  This DLL can
then be used "as usual" from an application; the application doesn't
need to know that it is talking with a library made with Python and
CFFI.  At runtime, when the application calls ``int do_stuff(int,
int)``, the Python interpreter is automatically initialized and ``def
do_stuff(x, y):`` gets called.  `See the details in the documentation
about embedding.`__

.. __: embedding.html
.. __: embedding.html


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
``cdef()``.  If you have several interdependent libraries to load,
you would call ``cdef()`` only once but ``dlopen()`` several times.

By opposition, the API mode works more closely like a C program: the C
linker (static or dynamic) is responsible for finding any symbol used.
You name the libraries in the ``libraries`` keyword argument to
``set_source()``, but never need to say which symbol comes
from which library.
Other common arguments to ``set_source()`` include ``library_dirs`` and
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
with problems, particularly on non-Windows platforms.

The most immediate drawback of the ABI level is that calling functions
needs to go through the very general *libffi* library, which is slow
(and not always perfectly tested on non-standard platforms).  The API
mode instead compiles a CPython C wrapper that directly invokes the
target function.  It is, comparatively, massively faster (and works
better than libffi ever can).

The more fundamental reason to prefer the API mode is that *the C
libraries are typically meant to be used with a C compiler.* You are not
supposed to do things like guess where fields are in the structures.
The "real example" above shows how CFFI uses a C compiler under the
hood: this example uses ``set_source(..., "C source...")`` and never
``dlopen()``.  When using this approach,
we have the advantage that we can use literally "``...``" at various places in
the ``cdef()``, and the missing information will be completed with the
help of the C compiler.  CFFI will turn this into a single C source file,
which contains the "C source" part unmodified, followed by some
"magic" C code and declarations derived from the ``cdef()``.  When
this C file is compiled, the resulting C extension module will contain
all the information we need---or the C compiler will give warnings or
errors, as usual e.g. if we misdeclare some function's signature.

Note that the "C source" part from ``set_source()`` can contain
arbitrary C code.  You can use this to declare some
more helper functions written in C.  To export
these helpers to Python, put their signature in the ``cdef()`` too.
(You can use the ``static`` C keyword in the "C source" part,
as in ``static int myhelper(int x) { return x * 42; }``,
because these helpers are only
referenced from the "magic" C code that is generated afterwards in the
same C file.)

This can be used for example to wrap "crazy" macros into more standard
C functions.  The extra layer of C can be useful for other reasons
too, like calling functions that expect some complicated argument
structures that you prefer to build in C rather than in Python.  (On
the other hand, if all you need is to call "function-like" macros,
then you can directly declare them in the ``cdef()`` as if they were
functions.)

The generated piece of C code should be the same independently on the
platform on which you run it (or the Python version), so in simple cases
you can directly distribute the pre-generated C code and treat it as a
regular C extension module (which depends on the ``_cffi_backend``
module, on CPython).  The special Setuptools lines in the `example
above`__ are meant for the more complicated cases where we need to
regenerate the C sources as well---e.g. because the Python script that
regenerates this file will itself look around the system to know what it
should include or not.

.. __: real-example_

Note that the "API level + in-line" mode combination exists but is long
deprecated.  It used to be done with ``lib = ffi.verify("C header")``.
The out-of-line variant with ``set_source("modname", "C header")`` is
preferred.
