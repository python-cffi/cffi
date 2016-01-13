================================
Using CFFI for embedding
================================

.. contents::

You can use CFFI to generate a ``.so/.dll`` which exports the API of
your choice to any C application that wants to link with this
``.so/.dll``.

This is entirely *new in version 1.5.*


Usage
-----

.. __: overview.html#embedding

See the `paragraph in the overview page`__ for a quick introduction.
In this section, we explain every step in more details.  We will use
here this slightly expanded example:

.. code-block:: c

    /* file plugin.h */
    typedef struct { int x, y; } point_t;
    extern int do_stuff(point_t *);

.. code-block:: python

    # file plugin_build.py
    import cffi
    ffi = cffi.FFI()

    with open('plugin.h') as f:
        ffi.embedding_api(f.read())

    ffi.set_source("my_plugin", '''
        #include "plugin.h"
    ''')

    ffi.embedding_init_code("""
        from my_plugin import ffi

        @ffi.def_extern()
        def do_stuff(p):
            print("adding %d and %d" % (p.x, p.y))
            return p.x + p.y
    """)

    ffi.compile(target="plugin-1.5.*", verbose=True)

Running the code above produces a *DLL*, i,e, a dynamically-loadable
library.  It is a file with the extension ``.dll`` on Windows or
``.so`` on other platforms.  As usual, it is produced by generating
some intermediate ``.c`` code and then calling the regular
platform-specific C compiler.

Here are some details about the methods used above:

* **ffi.embedding_api(source):** parses the given C source, which
  declares functions that you want to be exported by the DLL.  It can
  also declare types, constants and global variables that are part of
  the C-level API of your DLL.

  The functions that are found in ``source`` will be automatically
  defined in the ``.c`` file: they will contain code that initializes
  the Python interpreter the first time any of them is called,
  followed by code to call the attached Python function (with
  ``@ffi.def_extern()``, see next point).

  The global variables, on the other hand, are not automatically
  produced.  You have to write their definition explicitly in
  ``ffi.set_source()``, as regular C code (see the point after next).

* **ffi.embedding_init_code(python_code):** this gives
  initialization-time Python source code.  This code is copied inside
  the DLL.  At runtime, the code is executed when the DLL is first
  initialized, just after Python itself is initialized.  This newly
  initialized Python interpreter has got an extra module ready to be
  imported, typically with a line like "``from my_plugin import ffi,
  lib``".  The name ``my_plugin`` comes from the first argument to
  ``ffi.set_source()``.  (This module represents "the caller's C
  world" from the point of view of Python.)

  The initialization-time Python code can import other modules or
  packages as usual (it might need to set up ``sys.path`` first).  For
  every function declared within ``ffi.embedding_api()``, it should
  use the decorator ``@ffi.def_extern()`` to attach a corresponding
  Python function to it.  (Of course, the decorator can appear either
  directly in the initialization-time Python code, or in any other
  module that it imports.  The usual Python rules apply, e.g. you need
  "``from my_plugin import ffi``" in a module, otherwise you can't say
  ``@ffi.def_extern()``.)

  If the initialization-time Python code fails with an exception, then
  you get tracebacks printed to stderr.  If some function remains
  unattached but the C code calls it, an error message is also printed
  to stderr and the function returns zero/null.

* **ffi.set_source(c_module_name, c_code):** set the name of the
  module from Python's point of view.  It also gives more C code which
  will be included in the generated C code.  In trivial examples it
  can be an empty string.  It is where you would ``#include`` some
  other files, define global variables, and so on.  The macro
  ``CFFI_DLLEXPORT`` is available to this C code: it expands to the
  platform-specific way of saying "the following declaration should be
  exported from the DLL".  For example, you would put "``extern int
  my_glob;``" in ``ffi.embedding_api()`` and "``CFFI_DLLEXPORT int
  my_glob = 42;``" in ``ffi.set_source()``.

  Currently, any *type* declared in ``ffi.embedding_api()`` must also
  be present in the ``c_code``.  This is automatic if this code
  contains a line like ``#include "plugin.h"`` in the example above.

* **ffi.compile([target=...] [, verbose=True]):** make the C code and
  compile it.  By default, it produces a file called
  ``c_module_name.dll`` or ``c_module_name.so``, but the default can
  be changed with the optional ``target`` keyword argument.  You can
  use ``target="foo.*"`` with a literal ``*`` to ask for a file called
  ``foo.dll`` on Windows or ``foo.so`` elsewhere.  (One point of the
  separate ``target`` file name is to include characters not usually
  allowed in Python module names, like "``plugin-1.5.*``".)

  For more complicated cases, you can call instead
  ``ffi.emit_c_code("foo.c")`` and compile the resulting ``foo.c``
  file using other means.  CFFI's compilation logic is based on the
  standard library ``distutils`` package, which is really developed
  and tested for the purpose of making CPython extension modules, not
  other DLLs.


More reading
------------

If you're reading this page about embedding and you are not familiar
with CFFI already, here are a few pointers to what you could read
next:

* For the ``@ffi.def_extern()`` functions, integer C types are passed
  simply as Python integers; and simple pointers-to-struct and basic
  arrays are all straightforward enough.  However, sooner or later you
  will need to read about this topic in more details here__.

* ``@ffi.def_extern()``: see `documentation here,`__ notably on what
  happens if the Python function raises an exception.

* In embedding mode, the major direction is C code that calls Python
  functions.  This is the opposite of the regular extending mode of
  CFFI, in which the major direction is Python code calling C.  That's
  why the page `Using the ffi/lib objects`_ talks first about the
  latter, and why the direction "C code that calls Python" is
  generally referred to as "callbacks" in that page.  (If you also
  need to have your Python code call C code, read more about
  `Embedding and Extending`_ below.)

* ``ffi.embedding_api(source)``: follows the same syntax as
  ``ffi.cdef()``, `documented here.`__  You can use the "``...``"
  syntax as well, although in practice it may be less useful than it
  is for ``cdef()``.  On the other hand, it is expected that often the
  C sources that you need to give to ``ffi.embedding_api()`` would be
  exactly the same as the content of some ``.h`` file that you want to
  give to users of your DLL.  That's why the example above does this::

      with open('foo.h') as f:
          ffi.embedding(f.read())

  Note that a drawback of this approach is that ``ffi.embedding()``
  doesn't support ``#ifdef`` directives.  You may have to use a more
  convoluted expression like::

      with open('foo.h') as f:
          lines = [line for line in f if not line.startswith('#')]
          ffi.embedding(''.join(lines))

  As in the example above, you can also use the same ``foo.h`` from
  ``ffi.set_source()``::

      ffi.set_source('module_name', '#include "foo.h"')


.. __: using.html#working
.. __: using.html#def-extern
.. __: cdef.html#cdef

.. _`Using the ffi/lib objects`: using.html


Embedding and Extending
-----------------------

The embedding mode is not incompatible with the non-embedding mode of
CFFI.  The Python code can import not only ``ffi`` but also ``lib``
from the module you define.  This ``lib`` contains all the C symbols
that are available to Python.  This includes all functions and global
variables declared in ``ffi.embedding_api()`` (it is how you should
read/write the global variables from Python).

You can use *both* ``ffi.embedding_api()`` and ``ffi.cdef()`` in the
same build script.  You put in the former the declarations you want to
be exported by the DLL; you put in the latter only the C functions and
types that you want to share between C and Python, but not export from
the DLL.

As an example of that, consider the case where you would like to have
a DLL-exported C function written in C directly, maybe to handle some
cases before calling Python functions.  To do that, you must *not* put
the function's signature in ``ffi.embedding_api()``.  (Note that this
requires more hacks if you use ``ffi.embedding(f.read())``.)  You must
only write the custom function definition in ``ffi.set_source()``, and
prefix it with the macro CFFI_DLLEXPORT:

.. code-block:: c

    CFFI_DLLEXPORT int myfunc(int a, int b)
    {
        /* implementation here */
    }

This function can, if it wants, invoke Python functions using the
general mechanism of "callbacks" (technically a call from C to Python,
although in this case it is not calling anything back):

.. code-block:: python

    ffi.cdef("""
        extern "Python" int mycb(int);
    """)

    ffi.set_source("my_plugin", """

        static int mycb(int);   /* the callback: forward declaration, to make
                                   it accessible from the C code that follows */

        CFFI_DLLEXPORT int myfunc(int a, int b)
        {
            int product = a * b;   /* some custom C code */
            return mycb(product);
        }
    """)

and then the Python initialization code needs to contain the lines:

.. code-block:: python

    @ffi.def_extern()
    def mycb(x):
        print "hi, I'm called with x =", x
        return x * 10

This ``@ffi.def_extern`` is attaching a Python function to the C
callback ``mycb``, which in this case is not exported from the DLL.
Nevertheless, the automatic initialization of Python occurs at this
time, if it happens that ``mycb()`` is the first function called
from C.  (It does not happen when ``myfunc()`` is called: this is just
a C function, with no extra code magically inserted around it.  It
only happens when ``myfunc()`` calls ``mycb()``.)

As the above explanation hints, this is how ``ffi.embedding_api()``
actually implements function calls that directly invoke Python code;
here, we have merely decomposed it explicitly, in order to add some
custom C code in the middle.

In case you need to force, from C code, Python to be initialized
before the first ``@ffi.def_extern()`` is called, you can do so by
calling the C function ``cffi_start_python()`` with no argument.  It
returns an integer, 0 or -1, to tell if the initialization succeeded
or not.  Currently there is no way to prevent a failing initialization
from also dumping a traceback and more information to stderr.
