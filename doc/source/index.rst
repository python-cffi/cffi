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


Installation and Status
=======================================================

This code has been tested on Linux only.  It is known to contain
some cross-platform issues.  Work on Windows will be coming soon.

Requirements:

  * Python 2.6 or 2.7

  * pycparser 2.06: http://code.google.com/p/pycparser/

Installation as usual:

  * ``python setup.py install``

  * or you can directly import and use ``cffi``, but if you don't
    compile the ``_ffi_backend`` extension module, it will fall back
    to using internally ``ctypes`` (slower).


Examples
=======================================================


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
    p = C.getpwuid(0)
    assert str(p.pw_name) == 'root'

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


What actually happened?
-----------------------

The CFFI interface operates on the same level as C - you declare types
and functions using the same syntax as you would define them in C.  This
means that most of the documentation or examples can be copied straight
from the man pages.

The declarations can contain types, functions and global variables.  The
cdef in the above examples are just that - they declared "there is a
function in the C level with this given signature", or "there is a
struct type with this shape".

The ``dlopen()`` line loads libraries.  C has multiple namespaces - a
global one and local ones per library. In this example we load the
global one (``None`` as argument to ``dlopen()``) which always contains
the standard C library.  You get as a result a ``<FFILibrary>`` object
that has as attributes all symbols declared in the ``cdef()`` and coming
from this library.

The ``verify()`` line in the second example is an alternative: instead
of doing a ``dlopen``, it generates and compiles a piece of C code.
When using ``verify()`` you have the advantage that you can use ``...``
at various places in the ``cdef()``, and the missing information will
be completed with the help of the C compiler.  It also does checking,
to verify that your declarations are correct.  If the C compiler gives
warnings or errors, they are reported here.

Finally, the ``ffi.new()`` lines allocate C objects.  They are filled
with zeroes initially, unless the optional second argument is used.
If specified, this argument gives an "initializer", like you can use
with C code to initialize global variables.

The actual function calls should be obvious.



Reference
=======================================================

As a guideline: you have already seen in the above examples all the
major pieces except maybe ``ffi.cast()``.  The rest of this
documentation gives a more complete reference.


Declaring types and functions
-----------------------------

``ffi.cdef(source)`` parses the given C source.  This should be done
first.  It registers all the functions, types, and global variables in
the C source.  The types can be used immediately in 'ffi.new()' and
other functions.  Before you can access the functions and global
variables, you need to give ``ffi`` another piece of information: where
they actually come from (which you do with either ``ffi.dlopen()`` or
``ffi.verify()``).

The C source is parsed internally (using ``pycparser``).  This code
cannot contain ``#include``.  It should typically be a self-contained
piece of declarations extracted from a man page.  The only things it
can assume to exist are the standard types:

 * char, short, int, long, long long (both signed and unsigned)

 * float, double

 * intN_t, uintN_t (for N=8,16,32,64), intptr_t, uintptr_t, ptrdiff_t,
   size_t, ssize_t

As we will see on `the verification step`_ below, the declarations
can also contain ``...`` at various places as placeholders that are
completed only by during a call to ``verify()``.


Loading libraries
-----------------

``ffi.dlopen(libpath)``: this function opens a shared library and
returns a module-like library object.  You can use the library object to
call the functions previously declared by ``ffi.cdef()``, and to read or
write global variables.  Note that you can use a single ``cdef()`` to
declare functions from multiple libraries, as long as you load each of
them with ``dlopen()`` and access the functions from the correct one.

The ``libpath`` is the file name of the shared library, which can
contain a full path or not (in which case it is searched in standard
locations, as described in ``man dlopen``).  Alternatively, if
``libpath`` is None, it returns the standard C library (which can be
used to access the functions of glibc, on Linux).

This gives ABI-level access to the library: you need to have all types
declared manually exactly as they were while the library was made.  No
checking is done.  For this reason, we recommend to use ``ffi.verify()``
instead when possible.

Note that only functions and global variables are in library objects;
types exist in the ``ffi`` instance independently of library objects.
This is due to the C model: the types you declare in C are not tied to a
particular library, as long as you ``#include`` their headers; but you
cannot call functions from a library without linking it in your program.


The verification step
---------------------

``ffi.verify(source, ...)``: verifies that the current ffi signatures
compile on this machine, and return a dynamic library object.  The
dynamic library can be used to call functions and access global
variables declared by a previous 'ffi.cdef()'.  The library is compiled
by the C compiler: it gives you C-level API compatibility (including
calling macros, as long as you declared them as functions in
``ffi.cdef()``).  This differs from ``ffi.dlopen()``, which requires
ABI-level compatibility and must be called several times to open several
shared libraries.

On top of CPython, the new library is actually a CPython C extension
module.  This solution constrains you to have a C compiler (future work
will cache the compiled C code and let you distribute it to other
systems which don't have a C compiler).

The arguments to ``ffi.verify()`` are:

 * ``source``: C code that is pasted verbatim in the generated code (it
   is *not* parsed internally).  It should contain at least the
   necessary ``#include``.  It can also contain the complete
   implementation of some functions declared in ``cdef()``; this is
   useful if you really need to write a piece of C code, e.g. to access
   some advanced macros.

 * ``include_dirs``, ``define_macros``, ``undef_macros``, ``libraries``,
   ``library_dirs``, ``extra_objects``, ``extra_compile_args``,
   ``extra_link_args`` (keyword arguments): these are used when
   compiling the C code, and are passed directly to distutils_.

.. _distutils: http://docs.python.org/distutils/setupscript.html#describing-extension-modules

On the plus side, this solution gives more "C-like" flexibility:

 * functions taking or returning integer or float-point arguments can be
   misdeclared: if e.g. a function is declared by ``cdef()`` as taking a
   ``int``, but actually takes a ``long``, then the C compiler handles the
   difference.

 * other arguments are checked: you get a compilation warning or error
   if you pass a ``int *`` argument to a function expecting a ``long *``.

Moreover, you can use ``...`` in the following places in the ``cdef()``
for leaving details unspecified (filled in by the C compiler):

 * structure declarations: any ``struct`` that ends with ``...;`` is
   partial.  It will be completed by the compiler.  (You can only access
   fields that you declared; the compiler can only consider the missing
   fields as padding.)  Any ``struct`` declaration without ``...;`` is
   assumed to be exact, but this is checked: you get a
   ``VerificationError`` if it is not.

 * unknown types: the syntax ``typedef ... foo_t;`` declares the type
   ``foo_t`` as opaque.

 * array lengths: when used as structure fields, arrays can have an
   unspecified length, as in ``int n[];``.  The length is completed
   by the C compiler.

 * enums: in ``enum foo { A, B, C, ... };``, the enumerated values are
   not necessarily in order; the C compiler will reorder them as needed
   and skip any unmentioned value.  Like with structs, an ``enum`` that
   does not end in ``...`` is assumed to be exact, and this is checked.


Working with pointers, structures and arrays
--------------------------------------------

The C code's integers and floating-point values are mapped to Python's
regular ``int``, ``long`` and ``float``.  Moreover, the C type ``char``
correspond to single-character strings in Python.  (If you want it to
map to small integers, use either ``signed char`` or ``unsigned char``.)

Pointers, structures and arrays are more complex: they don't have an
obvious Python equivalent.  They correspond to objects of type
``cdata``, which are printed for example as ``<cdata 'struct foo_s *'>``.

``ffi.new(ctype [, initializer])``: this function builds a new cdata
object of the given ``ctype``.  The ctype is usually some constant
string describing the C type.  This is similar to a malloc: it allocates
the memory needed to store an object of the given C type, and returns a
pointer to it.  Unlike C, the returned pointer object has *ownership* on
the allocated memory: when this exact object is garbage-collected, then
the memory is freed.

The memory is initially filled with zeros.  An initializer can be given
too, as described later.

The cdata objects support mostly the same operations as in C: you can
read or write from pointers, arrays and structures.  Dereferencing a
pointer is done usually in C with the syntax ``*p``, which is not valid
Python, so instead you have to use the alternative syntax ``p[0]``
(which is also valid C).  Additionally, the ``p->x`` syntax in C becomes
``p.x`` in Python.

Any operation that would in C return a pointer or array or struct type
gives you a new cdata object.  Unlike the "original" one, these new
cdata objects don't have ownership: they are merely references to
existing memory.

Example::

    ffi.cdef("void somefunction(int *);")
    lib = ffi.verify("#include <foo.h>")

    x = ffi.new("int")        # allocate one int, and return a pointer to it
    x[0] = 42                 # fill it
    lib.somefunction(x)       # call the C function
    print x[0]                # read the possibly-changed value

The initializer given in ``ffi.new()`` can be mostly anything that you
would use as an initializer for C code, with lists or tuples instead of
using the C syntax ``{ .., .., .. }``.  And like C, arrays of chars can
also be initialized from a string, in which case a terminating null
character is appended implicitly.  Example::

    typedef struct { int x, y; } foo_t;

    static foo_t globvar = { 1, 2 };     // C syntax
    globvar = ffi.new("foo_t", [1, 2])   # CFFI equivalent

    static foo_t globvar = { .y=1, .x=2 };        // C syntax
    globvar = ffi.new("foo_t", {'y': 1, 'x': 2})  # CFFI equivalent

The C array types can have their length unspecified in C types, as long
as their length can be derived from the initializer, like in C::

    static int globvar[] = { 1, 2, 3, 4 };    // C syntax
    globvar = ffi.new("int[]", [1, 2, 3, 4])  # CFFI equivalent

As an extension, the initializer can also be just a number, giving
the length (in case you just want zero-initialization)::

    static int globvar[1000];           // C syntax
    globvar = ffi.new("int[1000]")      # CFFI 1st equivalent
    globvar = ffi.new("int[]", 1000)    # CFFI 2nd equivalent

This is useful if the length is not actually a constant, to avoid doing
things like ``ffi.new("int[%d]" % x)``, which is not recommended:
``ffi`` normally caches the string ``"int[]"`` to not need to re-parse
it all the time.



Indices and tables
==================

* :ref:`genindex`
* :ref:`search`

