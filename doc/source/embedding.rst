================================
Using CFFI for embedding
================================

.. contents::

From *version 1.5,* you can use CFFI to generate a ``.so/.dll`` which
exports the API of your choice to any C application that wants to link
with this ``.so/.dll``.


Usage
-----

See the `paragraph in the overview page`__ for a quick introduction.
In this section, we explain every step in more details.  We call *DLL*
the dynamically-loaded library that we are producing; it is a file
with the (default) extension ``.dll`` on Windows or ``.so`` on other
platforms.  As usual, it is produced by generating some intermediate
``.c`` code and then calling the regular platform-specific C compiler.

.. __: overview.html#embedding

* **ffi.embedding_api(source):** parses the given C source, which
  declares functions that you want to be exported by the DLL.  It can
  also declare types, constants and global variables that are part of
  the C-level API of your DLL.

  The functions are automatically defined in the ``.c`` file: they
  contain code that initializes the Python interpreter the first time
  any of them is called, followed by code to call the attached
  Python function (with ``@ffi.def_extern()``, see next point).

  The global variables, on the other hand, are not automatically
  produced; you have to write their definition explicitly in
  ``ffi.set_source()``, as regular C code.

* **ffi.embedding_init_code(python_code):** this gives
  initialization-time Python source code.  This code is copied inside
  the DLL.  At runtime, the code is executed when the DLL is first
  initialized, just after Python itself is initialized.  This newly
  initialized Python interpreter has got the DLL ready to be imported,
  typically with a line like ``from module_name import ffi, lib``
  (where ``module_name`` is the name given in first argument to
  ``ffi.set_source()``).

  This Python code can import other modules or packages as usual (it
  might need to set up ``sys.path`` first).  You should use the
  decorator ``@ffi.def_extern()`` to attach a Python function to each
  of the C functions declared within ``ffi.embedding_api()``.  (If you
  don't, calling the C function results for now in a message printed
  to stderr and a zero return value.)

* **ffi.set_source(module_name, c_code):** set the name of the module
  from Python's point of view.  It also gives more C code which will
  be included in the generated C code.  In simple examples it can be
  an empty string.  It is where you would ``#include`` some other
  files, define global variables, and so on.  The macro
  ``CFFI_DLLEXPORT`` is available to this C code: it expands to the
  platform-specific way of saying "the following declaration should be
  exported from the DLL".  For example, you would put "``int
  my_glob;``" in ``ffi.embedding_api()`` and "``CFFI_DLLEXPORT int
  my_glob = 42;``" in ``ffi.set_source()``.
  
* **ffi.compile([target=...] [, verbose=True]):** make the C code and
  compile it.  By default, it produces a file called
  ``module_name.dll`` or ``module_name.so``, but the default can be
  changed with the optional ``target`` keyword argument.  You can use
  ``target="foo.*"`` with a literal ``*`` to ask for a file called
  ``foo.dll`` on Windows or ``foo.so`` elsewhere.  (The ``target``
  file name can contain characters not usually allowed in Python
  module names.)

  For more complicated cases, you can call instead
  ``ffi.emit_c_code("foo.c")`` and compile the resulting ``foo.c``
  file using other means.  CFFI's compilation logic is based on the
  standard library ``distutils`` package, which is really developed
  and tested for the purpose of making CPython extension modules, not
  other DLLs.


More reading
------------

(XXX should point to a few places in the rest of the CFFI docs where
people starting from embedding would like to go next)

XXX copy the content of ffi.embedding() to a .h


Embedding and Extending
-----------------------

The embedding mode is not incompatible with the non-embedding mode of
CFFI.  The Python code can import not only ``ffi`` but also ``lib``
from the module you define.  This ``lib`` contains all the C symbols
that are available to Python.  This includes all functions and global
variables declared in ``ffi.embedding_api()`` (it is how you should
read/write the global variables from Python).

But you can use ``ffi.cdef()`` *in addition to*
``ffi.embedding_api()`` to exchange more C functions and global
variables between C and Python, without also making them exports of
the DLL.  See `here for more about cdef.`__

.. __: cdef.html#cdef

``ffi.cdef()`` is used to access functions and variables that you can,
and should, define as ``static`` in ``set_source()``.  On the other
hand, the C functions declared with ``ffi.embedding_api()`` work
similarly to ``extern "Python"`` functions from ``ffi.cdef()``.
See `here for more about extern "Python".`__  See `here for details
about @ffi.def_extern().`__

.. __: using.html#extern-python
.. __: using.html#extern-python-ref

In some cases, you want to write a DLL-exported C function in C
directly, maybe to handle some cases before calling Python functions.
To do that, you must *not* write the function's signature in
``ffi.embedding_api()``.  You must only write the custom function
definition in ``ffi.set_source()``, and prefix it with the macro
CFFI_DLLEXPORT:

.. code-block:: c

    CFFI_DLLEXPORT int myfunc(int a, int b)
    {
        /* implementation here */
    }

This function can, if it wants, invoke Python functions using the
general mechanism of "callbacks" (technically a call from C to Python,
although in this case it is not calling anything back): you need a
``ffi.cdef()`` with "``extern "Python" int mycb(int);``", and then you
can write this in ``ffi.set_source()``:

.. code-block:: c

    static int mycb(int);   /* the callback: forward declaration, to make
                               it accessible from the C code that follows */

    CFFI_DLLEXPORT int myfunc(int a, int b)
    {
        int product = a * b;   /* some custom C code */
        return mycb(product);
    }

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
we have merely decomposed it explicitly, in order to add some custom C
code in the middle.
