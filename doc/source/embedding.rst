================================
Using CFFI for embedding
================================

.. contents::

From *version 1.5,* you can use CFFI to generate a ``.so/.dll`` which
is no longer usable only from Python, but which exports the API of
your choice to any C application that wants to link with this
``.so/.dll``.


Usage
-----

See the `paragraph in the overview page`__ for a quick introduction.
We decompose and explain every step below.  We will call *DLL* the
dynamically-loaded library that we are producing; it is a file with
the (default) extension ``.dll`` on Windows or ``.so`` on other
platforms.  As usual, it is produced by generating some intermediate
``.c`` code and then calling the regular platform-specific C compiler.

.. __: overview.html#embedding

* **ffi.embedding_api(source):** parses the given C source, which
  declares functions that you want to be exported by the DLL.  It can
  also declare types, constants and global variables that are part of
  the C-level API of your DLL.

  The functions are automatically produced in the ``.c`` file: they
  contain code that initializes the Python interpreter the first time
  any of them is called, followed by code to call the associated
  Python function (see next point).

  The global variables, on the other hand, are not automatically
  produced; you have to write their definition explicitly in
  ``ffi.set_source()``, as regular C code.  (The C code, as usual, can
  include an initializer, or define the missing length for ``int
  glob[];``, for example).

* **ffi.embedding_init_code(python_code):** this stores the given
  Python source code inside the DLL.  This code will be executed at
  runtime when the DLL is first initialized, just after Python itself
  is initialized.  This Python interpreter runs with the DLL ready
  to be imported as a xxxxxxxxxxxxxx
  

  It should typically attach a Python function to each
  of the C functions declared in ``embedding_api()``.  It does this
  by importing the ``ffi`` object from the 
  
  with ``@ffi.def_extern()``.
