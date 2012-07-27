CFFI documentation
================================

.. toctree::
   :maxdepth: 2

Foreign Function Interface for Python calling C code. The aim of this project
is to provide a convenient and reliable way of calling C code from Python.
The interface is based on `LuaJIT's FFI`_ and follows a few principles:

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
  (ctypes_ works at the ABI level, whereas Cython_ and `native C extensions`_
  work at the API level.)

* We try to be complete.  For now some C99 constructs are not supported,
  but all C89 should be, including macros (and including macro "abuses",
  which you can `manually wrap`_ in saner-looking C functions).

* We attempt to support both PyPy and CPython (although PyPy support is not
  complete yet) with a reasonable path for other Python implementations like
  IronPython and Jython.

* Note that this project is **not** about embedding executable C code in
  Python, unlike `Weave`_.  This is about calling existing C libraries
  from Python.

.. _`LuaJIT's FFI`: http://luajit.org/ext_ffi.html
.. _`Cython`: http://www.cython.org
.. _`SWIG`: http://www.swig.org/
.. _`CPython native C extensions`: http://docs.python.org/extending/extending.html
.. _`native C extensions`: http://docs.python.org/extending/extending.html
.. _`ctypes`: http://docs.python.org/library/ctypes.html
.. _`Weave`: http://www.scipy.org/Weave
.. _`manually wrap`: `The verification step`_


Installation and Status
=======================================================

Quick installation:

* ``pip install cffi``

* or get the source code via the `Python Package Index`__.

.. __: http://pypi.python.org/pypi/cffi

In more details:

This code has been developed on Linux but should work on any POSIX
platform as well as on Win32.  There are some Windows-specific issues
left.

It currently supports CPython 2.x.  Support for CPython 3.x should not
be too hard.  Support for PyPy is coming soon.  (In fact, the authors of
CFFI are also on the PyPy team; we plan to make it the first (and
fastest) choice for PyPy.)

Requirements:

* CPython 2.6 or 2.7 (you need ``python-dev``)

* pycparser 2.06 or 2.07: http://code.google.com/p/pycparser/

* libffi (you need ``libffi-dev``); for Windows, it is included with CFFI.

* a C compiler is required to use CFFI during development, but not to run
  correctly-installed programs that use CFFI.

Download and Installation:

* https://bitbucket.org/cffi/cffi/downloads

  - https://bitbucket.org/cffi/cffi/get/release-0.2.1.tar.bz2 has
    a MD5 of xxx and SHA of xxx

  - or get it via ``hg clone https://bitbucket.org/cffi/cffi``

* ``python setup.py install`` or ``python setup_base.py install``
  (should work out of the box on Linux or Windows; see below for
  `MacOS 10.6`_)

* or you can directly import and use ``cffi``, but if you don't
  compile the ``_cffi_backend`` extension module, it will fall back
  to using internally ``ctypes`` (much slower and does not support
  ``verify()``; we recommend not to use it).

* running the tests: ``py.test c/ testing/ -x`` (if you didn't
  install cffi yet, you may need ``python setup_base.py build``
  and ``PYTHONPATH=build/lib.xyz.../``)

Demos:

* The `demo`_ directory contains a number of small and large demos
  of using ``cffi``.

* The documentation below is sketchy on the details; for now the
  ultimate reference is given by the tests, notably
  `testing/test_verify.py`_ and `testing/backend_tests.py`_.

.. _`demo`: https://bitbucket.org/cffi/cffi/src/default/demo
.. _`testing/backend_tests.py`: https://bitbucket.org/cffi/cffi/src/default/testing/backend_tests.py
.. _`testing/test_verify.py`: https://bitbucket.org/cffi/cffi/src/default/testing/test_verify.py


Platform-specific instructions
------------------------------

``libffi`` is notoriously messy to install and use --- to the point that
CPython includes its own copy to avoid relying on external packages.
CFFI does the same for Windows, but (so far) not for other platforms.
Modern Linuxes work out of the box thanks to ``pkg-config``.  Here are some
(user-supplied) instructions for other platforms.


MacOS 10.6
++++++++++

(Thanks Juraj Sukop for this)

For building libffi you can use the default install path, but then, in
``setup.py`` you need to change::

    include_dirs = []

to::

    include_dirs = ['/usr/local/lib/libffi-3.0.11/include']

Then running ``python setup.py build`` complains about "fatal error: error writing to -: Broken pipe", which can be fixed by running::

    ARCHFLAGS="-arch i386 -arch x86_64" python setup.py build

as described here_.

.. _here: http://superuser.com/questions/259278/python-2-6-1-pycrypto-2-3-pypi-package-broken-pipe-during-build


=======================================================

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
    >>> C.printf("hi there, %s!\n", arg)         # call printf
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
``struct passwd``.  It requires a C compiler the first time you run it,
unless the module is distributed and installed according to the
`Distributing modules using CFFI`_ intructions below.  See also the
note about `Cleaning up the __pycache__ directory`_.

You will find a number of larger examples using ``verify()`` in the
`demo`_ directory.

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
When using ``verify()`` you have the advantage that you can use "``...``"
at various places in the ``cdef()``, and the missing information will
be completed with the help of the C compiler.  It also does checking,
to verify that your declarations are correct.  If the C compiler gives
warnings or errors, they are reported here.

Finally, the ``ffi.new()`` lines allocate C objects.  They are filled
with zeroes initially, unless the optional second argument is used.
If specified, this argument gives an "initializer", like you can use
with C code to initialize global variables.

The actual function calls should be obvious.  It's like C.

=======================================================

Distributing modules using CFFI
=======================================================

If you use CFFI and ``verify()`` in a project that you plan to
distribute, other users will install it on machines that may not have a
C compiler.  Here is how to write a ``setup.py`` script using
``distutils`` in such a way that the extension modules are listed too.
This lets normal ``setup.py`` commands compile and package the C
extension modules too.

Example::
  
  from distutils.core import setup
  from distutils.extension import Extension

  # you must import at least the module(s) that define the ffi's
  # that you use in your application
  import yourmodule

  setup(...
        ext_modules=[yourmodule.ffi.verifier.get_extension()])

Usually that's all you need, but see the `Reference: verifier`_ section
for more details about the ``verifier`` object.


Cleaning up the __pycache__ directory
-------------------------------------

During development, every time you change the C sources that you pass to
``cdef()`` or ``verify()``, then the latter will create a new module
file name, based on the MD5 hash of these strings.  This creates more
and more files in the ``__pycache__`` directory.  It is recommended that
you clean it up from time to time.  A nice way to do that is to add, in
your test suite, a call to ``cffi.verifier.cleanup_tmpdir()``.
Alternatively, you can just completely remove the ``__pycache__``
directory.




=======================================================

Reference
=======================================================

As a guideline: you have already seen in the above examples all the
major pieces except maybe ``ffi.cast()``.  The rest of this
documentation gives a more complete reference.


Declaring types and functions
-----------------------------

``ffi.cdef(source)`` parses the given C source.  This should be done
first.  It registers all the functions, types, and global variables in
the C source.  The types can be used immediately in ``ffi.new()`` and
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

* wchar_t (if supported by the backend)

As we will see on `the verification step`_ below, the declarations can
also contain "``...``" at various places; these are placeholders that will
be completed by a call to ``verify()``.


Loading libraries
-----------------

``ffi.dlopen(libpath)``: this function opens a shared library and
returns a module-like library object.  You need to use *either*
``ffi.dlopen()`` *or* ``ffi.verify()``, documented below_.

You can use the library object to call the functions previously declared
by ``ffi.cdef()``, and to read or write global variables.  Note that you
can use a single ``cdef()`` to declare functions from multiple
libraries, as long as you load each of them with ``dlopen()`` and access
the functions from the correct one.

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
cannot call functions from a library without linking it in your program,
as ``dlopen()`` does dynamically in C.

.. _below:


The verification step
---------------------

``ffi.verify(source, **kwargs)``: verifies that the current ffi signatures
compile on this machine, and return a dynamic library object.  The
dynamic library can be used to call functions and access global
variables declared by a previous ``ffi.cdef()``.  You don't need to use
``ffi.dlopen()`` in this case.

The returned library is a custom one, compiled just-in-time by the C
compiler: it gives you C-level API compatibility (including calling
macros, as long as you declared them as functions in ``ffi.cdef()``).
This differs from ``ffi.dlopen()``, which requires ABI-level
compatibility and must be called several times to open several shared
libraries.

On top of CPython, the new library is actually a CPython C extension
module.

The arguments to ``ffi.verify()`` are:

*  ``source``: C code that is pasted verbatim in the generated code (it
   is *not* parsed internally).  It should contain at least the
   necessary ``#include``.  It can also contain the complete
   implementation of some functions declared in ``cdef()``; this is
   useful if you really need to write a piece of C code, e.g. to access
   some advanced macros (see the example of ``getyx()`` in
   `demo/_curses.py`_).

*  ``include_dirs``, ``define_macros``, ``undef_macros``, ``libraries``,
   ``library_dirs``, ``extra_objects``, ``extra_compile_args``,
   ``extra_link_args`` (keyword arguments): these are used when
   compiling the C code, and are passed directly to distutils_.

.. _distutils: http://docs.python.org/distutils/setupscript.html#describing-extension-modules
.. _`demo/_curses.py`: https://bitbucket.org/cffi/cffi/src/default/demo/_curses.py

On the plus side, this solution gives more "C-like" flexibility:

*  functions taking or returning integer or float-point arguments can be
   misdeclared: if e.g. a function is declared by ``cdef()`` as taking a
   ``int``, but actually takes a ``long``, then the C compiler handles the
   difference.

*  other arguments are checked: you get a compilation warning or error
   if you pass a ``int *`` argument to a function expecting a ``long *``.

Moreover, you can use "``...``" in the following places in the ``cdef()``
for leaving details unspecified, which are then completed by the C
compiler during ``verify()``:

*  structure declarations: any ``struct`` that ends with "``...;``" is
   partial: it may be missing fields and/or have them declared out of order.
   This declaration will be corrected by the compiler.  (But note that you
   can only access fields that you declared, not others.)  Any ``struct``
   declaration which doesn't use "``...``" is assumed to be exact, but this is
   checked: you get a ``VerificationError`` if it is not.

*  unknown types: the syntax "``typedef ... foo_t;``" declares the type
   ``foo_t`` as opaque.  Useful mainly for when the API takes and returns
   ``foo_t *`` without you needing to look inside the ``foo_t``.  Note that
   such an opaque struct has no known size, which prevents some operations
   from working (mostly like in C).  In some cases you need to say that
   ``foo_t`` is not opaque, but you just don't know any field in it; then
   you would use "``typedef struct { ...; } foo_t;``".

*  array lengths: when used as structure fields, arrays can have an
   unspecified length, as in "``int n[];``" or "``int n[...];``.
   The length is completed by the C compiler.

*  enums: in "``enum foo { A, B, C, ... };``" (with a trailing "``...``"),
   the enumerated values are not necessarily in order; the C compiler
   will reorder them as needed and skip any unmentioned value.  Like
   with structs, an ``enum`` that does not end in "``...``" is assumed to
   be exact, and this is checked.

*  integer macros: you can write in the ``cdef`` the line
   "``#define FOO ...``", with any macro name FOO.  Provided the macro
   is defined to be an integer value, this value will be available via
   an attribute of the library object returned by ``verify()``.  The
   same effect can be achieved by writing a declaration
   ``static const int FOO;``.  The latter is more general because it
   supports other types than integer types (note: the syntax is then
   to write the ``const`` together with the variable name, as in
   ``static char *const FOO;``).

Currently, finding automatically the size of an integer type is not
supported.  You need to declare them with ``typedef int myint;`` or
``typedef long myint;`` or ``typedef long long myint;`` or their
unsigned equivalent.  Depending on the usage, the C compiler might give
warnings if you misdeclare ``myint`` as the wrong type even if it is
equivalent on this platform (e.g. using ``long`` instead of ``long
long`` or vice-versa on 64-bit Linux).


Working with pointers, structures and arrays
--------------------------------------------

The C code's integers and floating-point values are mapped to Python's
regular ``int``, ``long`` and ``float``.  Moreover, the C type ``char``
corresponds to single-character strings in Python.  (If you want it to
map to small integers, use either ``signed char`` or ``unsigned char``.)

Similarly, the C type ``wchar_t`` corresponds to single-character
unicode strings, if supported by the backend.  Note that in some
situations (a narrow Python build with an underlying 4-bytes wchar_t
type), a single wchar_t character may correspond to a pair of
surrogates, which is represented as a unicode string of length 2.  If
you need to convert a wchar_t to an integer, do not use ``ord(x)``,
because it doesn't accept such unicode strings; use instead
``int(ffi.cast('int', x))``, which does.

Pointers, structures and arrays are more complex: they don't have an
obvious Python equivalent.  Thus, they correspond to objects of type
``cdata``, which are printed for example as
``<cdata 'struct foo_s *' 0xa3290d8>``.

``ffi.new(ctype, [initializer])``: this function builds and returns a
new cdata object of the given ``ctype``.  The ctype is usually some
constant string describing the C type.  It must be a pointer or array
type.  If it is a pointer, e.g. ``"int *"`` or ``struct foo *``, then
it allocates the memory for one ``int`` or ``struct foo``.  If it is
an array, e.g. ``int[10]``, then it allocates the memory for ten
``int``.  In both cases the returned cdata is of type ``ctype``.

The memory is initially filled with zeros.  An initializer can be given
too, as described later.

Example::

    >>> ffi.new("char *")
    <cdata 'char *' owning 1 bytes>
    >>> ffi.new("int *")
    <cdata 'int *' owning 4 bytes>
    >>> ffi.new("int[10]")
    <cdata 'int[10]' owning 40 bytes>

.. versionchanged:: 0.2
   Note that this changed from CFFI version 0.1: what used to be
   ``ffi.new("int")`` is now ``ffi.new("int *")``.

Unlike C, the returned pointer object has *ownership* on the allocated
memory: when this exact object is garbage-collected, then the memory is
freed.  If, at the level of C, you store a pointer to the memory
somewhere else, then make sure you also keep the object alive for as
long as needed.  (This also applies if you immediately cast the returned
pointer to a pointer of a different type: only the original object has
ownership, so you must keep it alive.  As soon as you forget it, then
the casted pointer will point to garbage.)

The cdata objects support mostly the same operations as in C: you can
read or write from pointers, arrays and structures.  Dereferencing a
pointer is done usually in C with the syntax ``*p``, which is not valid
Python, so instead you have to use the alternative syntax ``p[0]``
(which is also valid C).  Additionally, the ``p.x`` and ``p->x``
syntaxes in C both become ``p.x`` in Python.

.. versionchanged:: 0.2
   You will find ``ffi.NULL`` to use in the same places as the C ``NULL``.
   Like the latter, it is actually defined to be ``ffi.cast("void *", 0)``.
   In version 0.1, reading a NULL pointer used to return None;
   now it returns a regular ``<cdata 'type *' NULL>``, which you can
   check for e.g. by comparing it with ``ffi.NULL``.

There is no equivalent to the ``&`` operator in C (because it would not
fit nicely in the model, and it does not seem to be needed here).

Any operation that would in C return a pointer or array or struct type
gives you a fresh cdata object.  Unlike the "original" one, these fresh
cdata objects don't have ownership: they are merely references to
existing memory.

As an exception the above rule, dereferencing a pointer that owns a
*struct* or *union* object returns a cdata struct or union object
that "co-owns" the same memory.  Thus in this case there are two
objects that can keep the same memory alive.  This is done for cases where
you really want to have a struct object but don't have any convenient
place to keep alive the original pointer object (returned by
``ffi.new()``).

Example::

    ffi.cdef("void somefunction(int *);")
    lib = ffi.verify("#include <foo.h>")

    x = ffi.new("int *")      # allocate one int, and return a pointer to it
    x[0] = 42                 # fill it
    lib.somefunction(x)       # call the C function
    print x[0]                # read the possibly-changed value

The equivalent of C casts are provided with ``ffi.cast("type", value)``.
They should work in the same cases as they do in C.  Additionally, this
is the only way to get cdata objects of integer or floating-point type::

    >>> x = ffi.cast("int", 42)
    >>> x
    <cdata 'int' 42>
    >>> int(x)
    42

The initializer given as the optional second argument to ``ffi.new()``
can be mostly anything that you would use as an initializer for C code,
with lists or tuples instead of using the C syntax ``{ .., .., .. }``.
Example::

    typedef struct { int x, y; } foo_t;

    foo_t v = { 1, 2 };            // C syntax
    v = ffi.new("foo_t *", [1, 2]) # CFFI equivalent

    foo_t v = { .y=1, .x=2 };                // C99 syntax
    v = ffi.new("foo_t *", {'y': 1, 'x': 2}) # CFFI equivalent

Like C, arrays of chars can also be initialized from a string, in
which case a terminating null character is appended implicitly::

    >>> x = ffi.new("char[]", "hello")
    >>> x
    <cdata 'char[]' owning 6 bytes>
    >>> len(x)        # the actual size of the array
    6
    >>> x[5]          # the last item in the array
    '\x00'
    >>> x[0] = 'H'    # change the first item
    >>> str(x)        # interpret 'x' as a regular null-terminated string
    'Hello'

Similarly, arrays of wchar_t can be initialized from a unicode string,
and calling ``unicode()`` on the cdata object returns the current unicode
string stored in the wchar_t array (encoding and decoding surrogates as
needed if necessary).

Note that unlike Python lists or tuples, but like C, you *cannot* index in
a C array from the end using negative numbers.

More generally, the C array types can have their length unspecified in C
types, as long as their length can be derived from the initializer, like
in C::

    int array[] = { 1, 2, 3, 4 };           // C syntax
    array = ffi.new("int[]", [1, 2, 3, 4])  # CFFI equivalent

As an extension, the initializer can also be just a number, giving
the length (in case you just want zero-initialization)::

    int array[1000];                  // C syntax
    array = ffi.new("int[1000]")      # CFFI 1st equivalent
    array = ffi.new("int[]", 1000)    # CFFI 2nd equivalent

This is useful if the length is not actually a constant, to avoid things
like ``ffi.new("int[%d]" % x)``.  Indeed, this is not recommended:
``ffi`` normally caches the string ``"int[]"`` to not need to re-parse
it all the time.


An example of calling a main-like thing
---------------------------------------

Imagine we have something like this:

.. code-block:: python

   from cffi import FFI
   ffi = FFI()
   ffi.cdef("""
      int main_like(int argv, char *argv[]);
   """)

Now, everything is simple, except, how do we create the ``char**`` argument
here?
The first idea:

.. code-block:: python

   argv = ffi.new("char *[]", ["arg0", "arg1"])

Does not work, because the initializer receives python ``str`` instead of
``char*``. Now, the following would almost work:

.. code-block:: python

   argv = ffi.new("char *[]", [ffi.new("char[]", "arg0"),
                               ffi.new("char[]", "arg1")])

However, the two ``char[]`` objects will not be automatically kept alive.
To keep them alive, one solution is to make sure that the list is stored
somewhere for long enough.
For example:

.. code-block:: python

   argv_keepalive = [ffi.new("char[]", "arg0"),
                     ffi.new("char[]", "arg1")]
   argv = ffi.new("char *[]", argv_keepalive)

will work.

Function calls
--------------

When calling C functions, passing arguments follows mostly the same
rules as assigning to structure fields, and the return value follows the
same rules as reading a structure field.  For example::

    ffi.cdef("""
        int foo(short a, int b);
    """)
    lib = ffi.verify("#include <foo.h>")

    n = lib.foo(2, 3)     # returns a normal integer
    lib.foo(40000, 3)     # raises OverflowError

As an extension, you can pass to ``char *`` arguments a normal Python
string (but don't pass a normal Python string to functions that take a
``char *`` argument and may mutate it!)::

    ffi.cdef("""
        size_t strlen(const char *);
    """)
    C = ffi.dlopen(None)

    assert C.strlen("hello") == 5

So far passing unicode strings as ``wchar_t *`` arguments is not
implemented.  You need to write e.g.::
  
    >>> C.wcslen(ffi.new("wchar_t[]", u"foo"))
    3

CFFI supports passing and returning structs to functions and callbacks.
Example (sketch)::

    >>> ffi.cdef("""
    ...     struct foo_s { int a, b; };
    ...     struct foo_s function_returning_a_struct(void);
    ... """)
    >>> lib = ffi.verify("#include <somewhere.h>")
    >>> lib.function_returning_a_struct()
    <cdata 'struct foo_s' owning 8 bytes>

There are a few (obscure) limitations to the argument types and
return type.  You cannot pass directly as argument a union, nor a struct
which uses bitfields (note that passing a *pointer* to anything is
fine).  If you pass a struct, the struct type cannot have been declared
with "``...;``" and completed with ``verify()``; you need to declare it
completely in ``cdef()``.

Aside from these limitations, functions and callbacks can return structs.


Variadic function calls
-----------------------

Variadic functions in C (which end with "``...``" as their last
argument) can be declared and called normally, with the exception that
all the arguments passed in the variable part *must* be cdata objects.
This is because it would not be possible to guess, if you wrote this::

    C.printf("hello, %d\n", 42)

that you really meant the 42 to be passed as a C ``int``, and not a
``long`` or ``long long``.  The same issue occurs with ``float`` versus
``double``.  So you have to force cdata objects of the C type you want,
if necessary with ``ffi.cast()``::
  
    C.printf("hello, %d\n", ffi.cast("int", 42))
    C.printf("hello, %ld\n", ffi.cast("long", 42))
    C.printf("hello, %f\n", ffi.cast("double", 42))
    C.printf("hello, %s\n", ffi.new("char[]", "world"))


Callbacks
---------

C functions can also be viewed as ``cdata`` objects, and so can be
passed as callbacks.  To make new C callback objects that will invoke a
Python function, you need to use::

    >>> def myfunc(x, y):
    ...    return x + y
    ...
    >>> ffi.callback("int(*)(int, int)", myfunc)
    <cdata 'int(*)(int, int)' calling <function myfunc at 0xf757bbc4>>

Warning: like ffi.new(), ffi.callback() returns a cdata that has
ownership of its C data.  (In this case, the necessary C data contains
the libffi data structures to do a callback.)  This means that the
callback can only be invoked as long as this cdata object is alive.  If
you store the function pointer into C code, then make sure you also keep this
object alive for as long as the callback may be invoked.  (If you want
the callback to remain valid forever, store the object in a fresh global
variable somewhere.)

Note that callbacks of a variadic function type are not supported.

Windows: you can't yet specify the calling convention of callbacks.
(For regular calls, the correct calling convention should be
automatically inferred by the C backend.)

Be careful when writing the Python callback function: if it returns an
object of the wrong type, or more generally raises an exception, then
the exception cannot be propagated.  Instead, it is printed to stderr
and the C-level callback is made to return a default value.

The returned value in case of errors is 0 or null by default, but can be
specified with the ``error`` keyword argument to ``ffi.callback()``::

    >>> ffi.callback("int(*)(int, int)", myfunc, error=42)

In all cases the exception is printed to stderr, so this should be
used only as a last-resort solution.


Miscellaneous
-------------

``ffi.errno``: the value of ``errno`` received from the most recent C call
in this thread, and passed to the following C call, is available via
reads and writes of the property ``ffi.errno``.  On Windows we also save
and restore the ``GetLastError()`` value, but to access it you need to
declare and call the ``GetLastError()`` function as usual.

``ffi.buffer(pointer, [size])``: return a read-write buffer object that
references the raw C data pointed to by the given 'cdata', of 'size'
bytes.  The 'cdata' must be a pointer or an array.  To get a copy of it
in a regular string, call str() on the result.  If unspecified, the
default size of the buffer is ``sizeof(*pointer)`` or the whole size of
the array.  Getting a buffer is useful because you can read from it
without an extra copy, or write into it to change the original value;
you can use for example ``file.write()`` and ``file.readinto()`` with
such a buffer (for files opened in binary mode).  (Remember that like in
C, you use ``array + index`` to get the pointer to the index'th item of
an array.)

``ffi.typeof("C type" or cdata object)``: return an object of type
``<ctype>`` corresponding to the parsed string, or to the C type of the
cdata instance.  Usually you don't need to call this function or to
explicitly manipulate ``<ctype>`` objects in your code: any place that
accepts a C type can receive either a string or a pre-parsed ``ctype``
object (and because of caching of the string, there is no real
performance difference).  It can still be useful in writing typechecks,
e.g.::
  
    def myfunction(ptr):
        assert ffi.typeof(ptr) is ffi.typeof("foo_t*")
        ...

``ffi.sizeof("C type" or cdata object)``: return the size of the
argument in bytes.  The argument can be either a C type, or a cdata object,
like in the equivalent ``sizeof`` operator in C.

``ffi.alignof("C type")``: return the alignment of the C type.
Corresponds to the ``__alignof__`` operator in GCC.

``ffi.offsetof("C struct type", "fieldname")``: return the offset within
the struct of the given field.  Corresponds to ``offsetof()`` in C.

``ffi.getcname("C type" or <ctype>, extra="")``: return the string
representation of the given C type.  If non-empty, the "extra" string is
appended (or inserted at the right place in more complicated cases); it
can be the name of a variable to declare, or an extra part of the type
like ``"*"`` or ``"[5]"``.  For example
``ffi.getcname(ffi.typeof(x), "*")`` returns the string representation
of the C type "pointer to the same type than x".


Reference: conversions
----------------------

This section documents all the conversions that are allowed when
*writing into* a C data structure (or passing arguments to a function
call), and *reading from* a C data structure (or getting the result of a
function call).  The last column gives the type-specific operations
allowed.

+---------------+------------------------+------------------+----------------+
|    C type     |   writing into         | reading from     |other operations|
+===============+========================+==================+================+
|   integers    | an integer or anything | a Python int or  | int()          |
|               | on which int() works   | long, depending  |                |
|               | (but not a float!).    | on the type      |                |
|               | Must be within range.  |                  |                |
+---------------+------------------------+------------------+----------------+
|   ``char``    | a string of length 1   | a string of      | str(), int()   |
|               | or another <cdata char>| length 1         |                |
+---------------+------------------------+------------------+----------------+
|  ``wchar_t``  | a unicode of length 1  | a unicode of     | unicode(),     |
|               | (or maybe 2 if         | length 1         | int()          |
|               | surrogates) or         | (or maybe 2 if   |                |
|               | another <cdata wchar_t>| surrogates)      |                |
+---------------+------------------------+------------------+----------------+
|  ``float``,   | a float or anything on | a Python float   | float(), int() |
|  ``double``   | which float() works    |                  |                |
+---------------+------------------------+------------------+----------------+
|  pointers     | another <cdata> with   | a <cdata>        | ``[]``, ``+``, |
|               | a compatible type (i.e.|                  | ``-``          |
|               | same type or ``char*`` |                  |                |
|               | or ``void*``, or as an |                  |                |
|               | array instead)         |                  |                |
+---------------+------------------------+                  +----------------+
|  ``void *``   | another <cdata> with   |                  |                |
|               | any pointer or array   |                  |                |
|               | type                   |                  |                |
+---------------+------------------------+                  +----------------+
|  ``char *``   | another <cdata> with   |                  | ``[]``,        |
|               | any pointer or array   |                  | ``+``, ``-``,  |
|               | type, or               |                  | str()          |
|               | a Python string when   |                  |                |
|               | passed as func argument|                  |                |
+---------------+------------------------+                  +----------------+
| ``wchar_t *`` | same as pointers       |                  | ``[]``,        |
|               | (passing a unicode as  |                  | ``+``, ``-``,  |
|               | func argument is not   |                  | unicode()      |
|               | implemented)           |                  |                |
+---------------+------------------------+                  +----------------+
|  pointers to  | same as pointers       |                  | ``[]``,        |
|  structure or |                        |                  | ``+``, ``-``,  |
|  union        |                        |                  | and read/write |
|               |                        |                  | struct fields  |
+---------------+                        |                  +----------------+
| function      |                        |                  | call           |
| pointers      |                        |                  |                |
+---------------+------------------------+------------------+----------------+
|  arrays       | a list or tuple of     | a <cdata>        | len(), iter(), |
|               | items                  |                  | ``[]``,        |
|               |                        |                  | ``+``, ``-``   |
+---------------+------------------------+                  +----------------+
|  ``char[]``   | same as arrays, or a   |                  | len(), iter(), |
|               | Python string          |                  | ``[]``, ``+``, |
|               |                        |                  | ``-``, str()   |
+---------------+------------------------+                  +----------------+
| ``wchar_t[]`` | same as arrays, or a   |                  | len(), iter(), |
|               | Python unicode         |                  | ``[]``,        |
|               |                        |                  | ``+``, ``-``,  |
|               |                        |                  | unicode()      |
+---------------+------------------------+------------------+----------------+
| structure     | a list or tuple or     | a <cdata>        | read/write     |
|               | dict of the field      |                  | fields         |
|               | values, or a same-type |                  |                |
|               | <cdata>                |                  |                |
+---------------+------------------------+                  +----------------+
| union         | same as struct, but    |                  | read/write     |
|               | with at most one field |                  | fields         |
+---------------+------------------------+------------------+----------------+
| enum          | an integer, or the enum| the enum value   | int(), str()   |
|               | value as a string or   | as a string, or  |                |
|               | as ``"#NUMBER"``       | ``"#NUMBER"``    |                |
|               |                        | if out of range  |                |
+---------------+------------------------+------------------+----------------+


Reference: verifier
-------------------

For advanced use cases, the ``Verifier`` class from ``cffi.verifier``
can be instantiated directly.  It is normally instantiated for you by
``ffi.verify()``, and the instance is attached as ``ffi.verifier``.

- ``Verifier(ffi, preamble, **kwds)``: instantiate the class with an
  FFI object and a preamble, which is C text that will be pasted into
  the generated C source.  The keyword arguments are passed directly
  to `distutils when building the Extension object.`__

.. __: http://docs.python.org/distutils/setupscript.html#describing-extension-module

``Verifier`` objects have the following public attributes and methods:

- ``sourcefilename``: name of a C file.  Defaults to
  ``__pycache__/_cffi_MD5HASH.c``, with the ``MD5HASH`` part computed
  from the strings you passed to cdef() and verify() as well as the
  version numbers of Python and CFFI.  Can be changed before calling
  ``write_source()`` if you want to write the source somewhere else.

- ``modulefilename``: name of the ``.so`` file (or ``.pyd`` on Windows).
  Defaults to ``__pycache__/_cffi_MD5HASH.so``.  Can be changed before
  calling ``compile_module()``.

- ``get_module_name()``: extract the module name from ``modulefilename``.

- ``write_source(file=None)``: produces the C source of the extension
  module.  If ``file`` is specified, write it in that file (or file-like)
  object rather than to ``sourcefilename``.

- ``compile_module()``: writes the C source code (if not done already)
  and compiles it.  This produces a dynamic link library whose file is
  given by ``modulefilename``.

- ``load_library()``: loads the C module (if necessary, making it
  first).  Returns an instance of a FFILibrary class that behaves like
  the objects returned by ffi.dlopen(), but that delegates all
  operations to the C module.  This is what is returned by
  ``ffi.verify()``.

- ``get_extension()``: returns a distutils-compatible ``Extension`` instance.

The following are global functions in the ``cffi.verifier`` module:

- ``set_tmpdir(dirname)``: sets the temporary directory to use instead of
  ``__pycache__``.
  
- ``cleanup_tmpdir()``: cleans up the temporary directory by removing all
  files in it called ``_cffi_*.{c,so}`` as well as all files in the
  ``build`` subdirectory.




=================

Comments and bugs
=================

The best way to contact us is on the IRC ``#pypy`` channel of
``irc.freenode.net``.  Feel free to discuss matters either there or in
the `mailing list`_.  Please report to the `issue tracker`_ any bugs.

As a general rule, when there is a design issue to resolve, we pick the
solution that is the "most C-like".  We hope that this module has got
everything you need to access C code and nothing more.

--- the authors, Armin Rigo and Maciej Fijalkowski

.. _`issue tracker`: https://bitbucket.org/cffi/cffi/issues
.. _`mailing list`: https://groups.google.com/forum/#!forum/python-cffi



Indices and tables
==================

* :ref:`genindex`
* :ref:`search`

