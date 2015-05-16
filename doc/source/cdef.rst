======================================
Preparing and Distributing modules
======================================


The minimal versus the extended FFI class
-----------------------------------------

CFFI contains actually two different ``FFI`` classes.  The page `Using
the ffi/lib objects`_ describes the minimal functionality.  One of
these two classes contains an extended API, described below.

.. _`Using the ffi/lib objects`: using.html

The minimal class is what you get with the out-of-line approach when
you say ``from _example import ffi``.  The extended class is what you
get when you say instead::

    import cffi

    ffi = cffi.FFI()

Only the latter kind contains the methods described below, which are
needed to make FFI objects from scratch or to compile them into
out-of-line modules.

The reason for this split of functionality is that out-of-line FFI
objects can be used without loading at all the ``cffi`` package.  In
fact, a regular program using CFFI out-of-line does not need anything
from the ``cffi`` pure Python package at all (but still needs
``_cffi_backend``, a C extension module).


Declaring types and functions
-----------------------------

**ffi.cdef(source)**: parses the given C source.
It registers all the functions, types, constants and global variables in
the C source.  The types can be used immediately in ``ffi.new()`` and
other functions.  Before you can access the functions and global
variables, you need to give ``ffi`` another piece of information: where
they actually come from (which you do with either ``ffi.dlopen()`` or
``ffi.set_source()/ffi.compile()``).

.. _`all types listed above`:

The C source is parsed internally (using ``pycparser``).  This code
cannot contain ``#include``.  It should typically be a self-contained
piece of declarations extracted from a man page.  The only things it
can assume to exist are the standard types:

* char, short, int, long, long long (both signed and unsigned)

* float, double, long double

* intN_t, uintN_t (for N=8,16,32,64), intptr_t, uintptr_t, ptrdiff_t,
  size_t, ssize_t

* wchar_t (if supported by the backend)

* _Bool and bool (equivalent).  If not directly supported by the C
  compiler, this is declared with the size of ``unsigned char``.

* FILE.  You can declare C functions taking a ``FILE *`` argument and
  call them with a Python file object.  If needed, you can also do
  ``c_f = ffi.cast("FILE *", fileobj)`` and then pass around ``c_f``.

* all `common Windows types`_ are defined if you run
  on Windows (``DWORD``, ``LPARAM``, etc.).  *Changed in version 0.9:* the
  types ``TBYTE TCHAR LPCTSTR PCTSTR LPTSTR PTSTR PTBYTE PTCHAR`` are no
  longer automatically defined; see `ffi.set_unicode()`_.

* *New in version 0.9.3:* the other standard integer types from
  stdint.h, like ``intmax_t``, as long as they map to integers of 1,
  2, 4 or 8 bytes.  Larger integers are not supported.

.. _`common Windows types`: http://msdn.microsoft.com/en-us/library/windows/desktop/aa383751%28v=vs.85%29.aspx

.. "versionadded:: 0.9.3": intmax_t etc.

The declarations can also contain "``...``" at various places; these are
placeholders that will be completed by the compiler.  More information
about it in the next section.

Note that all standard type names listed above are handled as
*defaults* only (apart from the ones that are keywords in the C
language).  If your ``cdef`` contains an explicit typedef that
redefines one of the types above, then the default described above is
ignored.  (This is a bit hard to implement cleanly, so in some corner
cases it might fail, notably with the error ``Multiple type specifiers
with a type tag``.  Please report it as a bug if it does.)

.. versionadded:: 0.8.2
   The ``ffi.cdef()`` call takes an optional
   argument ``packed``: if True, then all structs declared within
   this cdef are "packed".  If you need both packed and non-packed
   structs, use several cdefs in sequence.)  This
   has a meaning similar to ``__attribute__((packed))`` in GCC.  It
   specifies that all structure fields should have an alignment of one
   byte.  (Note that the packed attribute has no effect on bit fields so
   far, which mean that they may be packed differently than on GCC.
   Also, this has no effect on structs declared with ``"...;"``---next
   section.)


Letting the C compiler fill the gaps
------------------------------------

If you are using a C compiler (see `API-level`_), then:

*  functions taking or returning integer or float-point arguments can be
   misdeclared: if e.g. a function is declared by ``cdef()`` as taking a
   ``int``, but actually takes a ``long``, then the C compiler handles the
   difference.

*  other arguments are checked: you get a compilation warning or error
   if you pass a ``int *`` argument to a function expecting a ``long *``.

*  similarly, most things declared in the ``cdef()`` are checked, to
   the best we implemented so far; mistakes give compilation warnings
   or errors.

Moreover, you can use "``...``" (literally, dot-dot-dot) in the
``cdef()`` at various places, in order to ask the C compiler to fill
in the details.  These places are:

*  structure declarations: any ``struct { }`` that ends with "``...;``" as
   the last "field" is
   partial: it may be missing fields and/or have them declared out of order.
   This declaration will be corrected by the compiler.  (But note that you
   can only access fields that you declared, not others.)  Any ``struct``
   declaration which doesn't use "``...``" is assumed to be exact, but this is
   checked: you get an error if it is not.

*  unknown types: the syntax "``typedef ... foo_t;``" declares the type
   ``foo_t`` as opaque.  Useful mainly for when the API takes and returns
   ``foo_t *`` without you needing to look inside the ``foo_t``.  Also
   works with "``typedef ... *foo_p;``" which declares the pointer type
   ``foo_p`` without giving a name to the opaque type itself.  Note that
   such an opaque struct has no known size, which prevents some operations
   from working (mostly like in C).  *You cannot use this syntax to
   declare a specific type, like an integer type!  It declares opaque
   struct-like types only.*  In some cases you need to say that
   ``foo_t`` is not opaque, but just a struct where you don't know any
   field; then you would use "``typedef struct { ...; } foo_t;``".

*  array lengths: when used as structure fields or in global variables,
   arrays can have an unspecified length, as in "``int n[...];``".  The
   length is completed by the C compiler.  (Only the outermost array
   may have an unknown length, in case of array-of-array.)
   This is slightly different from "``int n[];``", because the latter
   means that the length is not known even to the C compiler.

*  enums: if you don't know the exact order (or values) of the declared
   constants, then use this syntax: "``enum foo { A, B, C, ... };``"
   (with a trailing "``...``").  The C compiler will be used to figure
   out the exact values of the constants.  An alternative syntax is
   "``enum foo { A=..., B, C };``" or even
   "``enum foo { A=..., B=..., C=... };``".  Like
   with structs, an ``enum`` without "``...``" is assumed to
   be exact, and this is checked.

*  integer constants and macros: you can write in the ``cdef`` the line
   "``#define FOO ...``", with any macro name FOO but with ``...`` as
   a value.  Provided the macro
   is defined to be an integer value, this value will be available via
   an attribute of the library object.  The
   same effect can be achieved by writing a declaration
   ``static const int FOO;``.  The latter is more general because it
   supports other types than integer types (note: the C syntax is then
   to write the ``const`` together with the variable name, as in
   ``static char *const FOO;``).

Currently, it is not supported to find automatically which of the
various integer or float types you need at which place.  In the case of
function arguments or return type, when it is a simple integer/float
type, it may be misdeclared (if you misdeclare a function ``void
f(long)`` as ``void f(int)``, it still works, but you have to call it
with arguments that fit an int).  But it doesn't work any longer for
more complex types (e.g. you cannot misdeclare a ``int *`` argument as
``long *``) or in other locations (e.g. a global array ``int a[5];``
must not be misdeclared ``long a[5];``).  CFFI considers `all types listed
above`_ as primitive (so ``long long a[5];`` and ``int64_t a[5]`` are
different declarations).


Preparing out-of-line modules
-----------------------------

**ffi.set_source(module_name, c_header_source, [\*\*keywords...])**:
prepare the ffi for producing out-of-line an external module called
``module_name``.  *New in version 1.0.*

The final goal is to produce an external module so that ``from
module_name import ffi`` gives a fast-loading, and possibly
C-compiler-completed, version of ``ffi``.  This method
``ffi.set_source()`` is typically called from a separate
``*_build.py`` file that only contains the logic to build this
external module.  Note that ``ffi.set_source()`` by itself does not
write any file, but merely records its arguments for later.  It can be
called before the ``ffi.cdef()`` or after.  See examples in the
overview_.

.. _overview: overview.html

The ``module_name`` can be a dotted name, in case you want to generate
the module inside a package.

The ``c_header_source`` is either some C source code or None.  If it
is None, the external module produced will be a pure Python module; no
C compiler is needed, but you cannot use the ``"..."`` syntax in the
``cdef()``.

On the other hand, if ``c_header_source`` is not None, then you can
use ``"..."`` in the ``cdef()``.  In this case, you must plan the
``c_header_source`` to be a string containing C code that will be
directly pasted in the generated C "source" file, like this::

    ...some internal declarations using the '_cffi_' prefix...

    "c_header_source", pasted directly

    ...some magic code to complete all the "..." from the cdef
    ...declaration of helper functions and static data structures
    ...and some standard CPython C extension module code

This makes a CPython C extension module (with a tweak to be
efficiently compiled on PyPy too).  The ``c_header_source`` should
contain the ``#include`` and other declarations needed to bring in all
functions, constants, global variables and types mentioned in the
``cdef()``.  The "magic code" that follows will complete, check, and
describe them as static data structures.  When you finally import this
module, these static data structures will be attached to the ``ffi``
and ``lib`` objects.

The ``keywords`` arguments are XXXXXXXXX


Compiling out-of-line modules
-----------------------------

Once an FFI object has been prepared, we must really generate the
.py/.c and possibly compile it.  There are several ways.

**ffi.compile(tmpdir='.'):** explicitly generate the .py/.c and (in
the second case) compile it.  The output file(s) are in the directory
given by ``tmpdir``.  This is suitable for
xxxxxxxxxxxxx



.. _loading-libraries:

ABI level: Loading libraries
----------------------------

``ffi.dlopen(libpath, [flags])``: this function opens a shared library and
returns a module-like library object.  Use this when you are fine with
the limitations of ABI-level access to the system.  In case of doubt, read
again `ABI versus API`_ in the overview.

.. _`ABI versus API`: overflow.html#abi-versus-api

You can use the library object to call the functions previously
declared by ``ffi.cdef()``, to read constants, and to read or write
global variables.  Note that you can use a single ``cdef()`` to
declare functions from multiple libraries, as long as you load each of
them with ``dlopen()`` and access the functions from the correct one.

The ``libpath`` is the file name of the shared library, which can
contain a full path or not (in which case it is searched in standard
locations, as described in ``man dlopen``), with extensions or not.
Alternatively, if ``libpath`` is None, it returns the standard C library
(which can be used to access the functions of glibc, on Linux).

Let me state it again: this gives ABI-level access to the library, so
you need to have all types declared manually exactly as they were
while the library was made.  No checking is done.

Note that only functions and global variables are in library objects;
types exist in the ``ffi`` instance independently of library objects.
This is due to the C model: the types you declare in C are not tied to a
particular library, as long as you ``#include`` their headers; but you
cannot call functions from a library without linking it in your program,
as ``dlopen()`` does dynamically in C.

For the optional ``flags`` argument, see ``man dlopen`` (ignored on
Windows).  It defaults to ``ffi.RTLD_NOW``.

This function returns a "library" object that gets closed when it goes
out of scope.  Make sure you keep the library object around as long as
needed.  (Alternatively, the out-of-line FFIs have a method
``ffi.dlclose()``.)



**ffi.include(other_ffi)**: includes the typedefs, structs, unions, enums
and constants defined in another FFI instance.  Usage is similar to a
``#include`` in C, where a part of the program might include types
defined in another part for its own usage.  Note that the include()
method has no effect on functions, constants and global variables, which
must anyway be accessed directly from the ``lib`` object returned by the
original FFI instance.  *Note that you should only use one ffi object
per library; the intended usage of ffi.include() is if you want to
interface with several inter-dependent libraries.*  For only one
library, make one ``ffi`` object.  (If the source becomes too large,
split it up e.g. by collecting the cdef/verify strings from multiple
Python modules, as long as you call ``ffi.verify()`` only once.)  *New
in version 0.5.*

.. "versionadded:: 0.5" --- inlined in the previous paragraph




Unimplemented features
----------------------

All of the ANSI C declarations should be supported, and some of C99.
Known missing features that are GCC or MSVC extensions:

* Any ``__attribute__`` or ``#pragma pack(n)``

* Additional types: complex numbers, special-size floating and fixed
  point types, vector types, and so on.  You might be able to access an
  array of complex numbers by declaring it as an array of ``struct
  my_complex { double real, imag; }``, but in general you should declare
  them as ``struct { ...; }`` and cannot access them directly.  This
  means that you cannot call any function which has an argument or
  return value of this type (this would need added support in libffi).
  You need to write wrapper functions in C, e.g. ``void
  foo_wrapper(struct my_complex c) { foo(c.real + c.imag*1j); }``, and
  call ``foo_wrapper`` rather than ``foo`` directly.

* Thread-local variables (access them via getter/setter functions)

.. _`variable-length array`:

.. versionadded:: 0.8
   Now supported: variable-length structures, i.e. whose last field is
   a variable-length array.

Note that since version 0.8, declarations like ``int field[];`` in
structures are interpreted as variable-length structures.  When used for
structures that are not, in fact, variable-length, it works too; in this
case, the difference with using ``int field[...];`` is that, as CFFI
believes it cannot ask the C compiler for the length of the array, you
get reduced safety checks: for example, you risk overwriting the
following fields by passing too many array items in the constructor.


Debugging dlopen'ed C libraries
-------------------------------

A few C libraries are actually hard to use correctly in a ``dlopen()``
setting.  This is because most C libraries are intented for, and tested
with, a situation where they are *linked* with another program, using
either static linking or dynamic linking --- but from a program written
in C, at start-up, using the linker's capabilities instead of
``dlopen()``.

This can occasionally create issues.  You would have the same issues in
another setting than CFFI, like with ``ctypes`` or even plain C code that
calls ``dlopen()``.  This section contains a few generally useful
environment variables (on Linux) that can help when debugging these
issues.

**export LD_TRACE_LOADED_OBJECTS=all**

    provides a lot of information, sometimes too much depending on the
    setting.  Output verbose debugging information about the dynamic
    linker. If set to ``all`` prints all debugging information it has, if
    set to ``help`` prints a help message about which categories can be
    specified in this environment variable

**export LD_VERBOSE=1**

    (glibc since 2.1) If set to a nonempty string, output symbol
    versioning information about the program if querying information
    about the program (i.e., either ``LD_TRACE_LOADED_OBJECTS`` has been set,
    or ``--list`` or ``--verify`` options have been given to the dynamic
    linker).

**export LD_WARN=1**

    (ELF only)(glibc since 2.1.3) If set to a nonempty string, warn
    about unresolved symbols.







**ffi.set_unicode(enabled_flag)**: Windows: if ``enabled_flag`` is
True, enable the ``UNICODE`` and ``_UNICODE`` defines in C, and
declare the types ``TBYTE TCHAR LPCTSTR PCTSTR LPTSTR PTSTR PTBYTE
PTCHAR`` to be (pointers to) ``wchar_t``.  If ``enabled_flag`` is
False, declare these types to be (pointers to) plain 8-bit characters.
(These types are not predeclared at all if you don't call
``set_unicode()``.)  *New in version 0.9.*

The reason behind this method is that a lot of standard functions have
two versions, like ``MessageBoxA()`` and ``MessageBoxW()``.  The
official interface is ``MessageBox()`` with arguments like
``LPTCSTR``.  Depending on whether ``UNICODE`` is defined or not, the
standard header renames the generic function name to one of the two
specialized versions, and declares the correct (unicode or not) types.

Usually, the right thing to do is to call this method with True.  Be
aware (particularly on Python 2) that, afterwards, you need to pass unicode
strings as arguments instead of not byte strings.  (Before cffi version 0.9,
``TCHAR`` and friends where hard-coded as unicode, but ``UNICODE`` was,
inconsistently, not defined by default.)

.. "versionadded:: 0.9" --- inlined in the previous paragraph


Reference: verifier
-------------------

missing




*  ``source``: C code that is pasted verbatim in the generated code (it
   is *not* parsed internally).  It should contain at least the
   necessary ``#include``.  It can also contain the complete
   implementation of some functions declared in ``cdef()``; this is
   useful if you really need to write a piece of C code, e.g. to access
   some advanced macros (see the example of ``getyx()`` in
   `demo/_curses.py`_).

*  ``sources``, ``include_dirs``,
   ``define_macros``, ``undef_macros``, ``libraries``,
   ``library_dirs``, ``extra_objects``, ``extra_compile_args``,
   ``extra_link_args`` (keyword arguments): these are used when
   compiling the C code, and are passed directly to distutils_.  You
   typically need at least ``libraries=['foo']`` in order to link with
   ``libfoo.so`` or ``libfoo.so.X.Y``, or ``foo.dll`` on Windows.  The
   ``sources`` is a list of extra .c files compiled and linked together.  See
   the distutils documentation for `more information about the other
   arguments`__.

.. __: http://docs.python.org/distutils/setupscript.html#library-options
.. _distutils: http://docs.python.org/distutils/setupscript.html#describing-extension-modules
.. _`demo/_curses.py`: https://bitbucket.org/cffi/cffi/src/default/demo/_curses.py

.. versionadded:: 0.4
   The ``tmpdir`` argument to ``verify()`` controls where the C
   files are created and compiled. Unless the ``CFFI_TMPDIR`` environment
   variable is set, the default is
   ``directory_containing_the_py_file/__pycache__`` using the
   directory name of the .py file that contains the actual call to
   ``ffi.verify()``.  (This is a bit of a hack but is generally
   consistent with the location of the .pyc files for your library.
   The name ``__pycache__`` itself comes from Python 3.)

   The ``ext_package`` argument controls in which package the
   compiled extension module should be looked from.  This is
   only useful after `distributing modules using CFFI`_.

   The ``tag`` argument gives an extra string inserted in the
   middle of the extension module's name: ``_cffi_<tag>_<hash>``.
   Useful to give a bit more context, e.g. when debugging.

.. _`warning about modulename`:

.. versionadded:: 0.5
   The ``modulename`` argument can be used to force a specific module
   name, overriding the name ``_cffi_<tag>_<hash>``.  Use with care,
   e.g. if you are passing variable information to ``verify()`` but
   still want the module name to be always the same (e.g. absolute
   paths to local files).  In this case, no hash is computed and if
   the module name already exists it will be reused without further
   check.  Be sure to have other means of clearing the ``tmpdir``
   whenever you change your sources.

.. versionadded:: 0.9
   You can give C++ source code in ``ffi.verify()``:

::

     ext = ffi.verify(r'''
         extern "C" {
             int somefunc(int somearg) { return real_cpp_func(somearg); }
         }
     ''', source_extension='.cpp', extra_compile_args=['-std=c++11'])

.. versionadded:: 0.9
   The optional ``flags`` argument has been added, see ``man dlopen`` (ignored
   on Windows).  It defaults to ``ffi.RTLD_NOW``.

.. versionadded:: 0.9
   The optional ``relative_to`` argument is useful if you need to list
   local files passed to the C compiler:

::

     ext = ffi.verify(..., sources=['foo.c'], relative_to=__file__)

The line above is roughly the same as::

     ext = ffi.verify(..., sources=['/path/to/this/file/foo.c'])

except that the default name of the produced library is built from the
CRC checkum of the argument ``sources``, as well as most other arguments
you give to ``ffi.verify()`` -- but not ``relative_to``.  So if you used
the second line, it would stop finding the already-compiled library
after your project is installed, because the ``'/path/to/this/file'``
suddenly changed.  The first line does not have this problem.






.. __: `Declaring types and functions`_

Note the following hack to find explicitly the size of any type, in
bytes::

    ffi.cdef("const int mysize;")
    lib = ffi.verify("const int mysize = sizeof(THE_TYPE);")
    print lib.mysize

Note that this approach is meant to call C libraries that are *not* using
``#include <Python.h>``.  The C functions are called without the GIL,
and afterwards we don't check if they set a Python exception, for
example.  You may work around it, but mixing CFFI with ``Python.h`` is
not recommended.
