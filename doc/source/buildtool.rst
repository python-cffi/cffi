.. _buildtool_docs:

=========================================
Building and Distributing CFFI Extensions
=========================================

.. contents::

CFFI ships a small subpackage, :mod:`cffi.buildtool`, together with a
command-line program, ``gen-cffi-src``. Both produce the same output as
:meth:`FFI.emit_c_code`: a ``.c`` source file ready to be compiled into
a CPython extension module. What they add is two convenient front-ends
-- one that executes an existing "build" Python script, and one that
reads a ``cdef`` and C prelude from two files. This tool enables
integrating with and build backend, such as `meson-python
<https://meson-python.readthedocs.io/>`_, `scikit-build-core
<https://scikit-build-core.readthedocs.io/>`_, or similar.

The rest of this page uses meson-python in the examples, but any PEP
517 backend that lets you run a helper program during the build can
drive ``gen-cffi-src`` the same way.

The ``cffi.buildtool`` subpackage was integrated from the
`cffi-buildtool`_ project by Rose Davidson (@inklesspen on GitHub).

.. _cffi-buildtool: https://github.com/inklesspen/cffi-buildtool


Python API for ``cffi.buildtool``
=================================

.. py:module:: cffi.buildtool

.. py:function:: find_ffi_in_python_script(pysrc, filename, ffivar)

   Execute a Python build script and return the :class:`cffi.FFI`
   object it defines. ``pysrc`` is the text of the script,
   ``filename`` is used for diagnostics, and ``ffivar`` is the name
   the script binds to the :class:`FFI` (or to a callable returning
   one -- typical ``ffibuilder`` names are supported). The script is
   executed with ``__name__`` set to ``"gen-cffi-src"`` so a trailing
   ``if __name__ == "__main__": ffibuilder.compile()`` block is
   skipped.

.. py:function:: make_ffi_from_sources(modulename, cdef, csrc)

   Build an :class:`cffi.FFI` from a ``cdef`` string and a C source
   prelude. Equivalent to::

     ffi = FFI()
     ffi.cdef(cdef)
     ffi.set_source(modulename, csrc)

.. py:function:: generate_c_source(ffi)

   Return the C source that :meth:`FFI.emit_c_code` would write for
   the given :class:`cffi.FFI`, as a :class:`str`.


The ``gen-cffi-src`` Command-line Tool
======================================

``gen-cffi-src`` has two subcommands. In both, the final positional
argument is the path to the ``.c`` file to generate.

.. note::

   When you drive the build from a build backend, the
   ``libraries=``, ``library_dirs=``, ``include_dirs=``,
   ``extra_compile_args=`` etc. arguments you pass to
   :meth:`FFI.set_source` are *ignored*. Link and include settings are
   the build backend's responsibility; for meson-python you express
   them through the ``dependencies:`` / ``include_directories:``
   arguments of ``py.extension_module()``.


``gen-cffi-src exec-python``
----------------------------

This mode takes the Python build script you would normally run by
hand -- the one the CFFI docs show under "Main mode of usage" -- and
generates the ``.c`` source for you. For example, given this
``_squared_build.py``::

  from cffi import FFI

  ffibuilder = FFI()

  ffibuilder.cdef("int square(int n);")

  ffibuilder.set_source(
      "squared._squared",
      '#include "square.h"',
  )

  if __name__ == "__main__":
      ffibuilder.compile(verbose=True)

you run:

.. code-block:: console

    $ gen-cffi-src exec-python _squared_build.py _squared.c

If the :class:`cffi.FFI` is bound to a name other than ``ffibuilder``,
pass ``--ffi-var``:

.. code-block:: console

    $ gen-cffi-src exec-python --ffi-var=make_ffi _squared_build.py _squared.c

``gen-cffi-src read-sources``
-----------------------------

For larger modules, keeping the ``cdef`` and the C source prelude in
separate files tends to be easier to work with -- your editor
treats them as plain C, and presubmit tooling doesn't have to parse
them out of a string literal.

Given ``squared.cdef.txt``:

.. code-block:: C

   int square(int n);

and ``squared.csrc.c``:

.. code-block:: C

   #include "square.h"

you run:

.. code-block:: console

   $ gen-cffi-src read-sources squared._squared squared.cdef.txt squared.csrc.c _squared.c

The first positional argument is the fully qualified module name that
will be embedded in the generated source (equivalent to the first
argument to :meth:`FFI.set_source`).


A Worked Example Using ``meson-python``
=======================================

Project layout:

.. code-block:: text

  squared/
  ├── pyproject.toml
  ├── meson.build
  └── src/
      ├── squared/
      │   ├── __init__.py
      │   └── _squared_build.py
      └── csrc/
          ├── square.h
          └── square.c

``pyproject.toml``:

.. code-block:: toml

  [build-system]
  build-backend = 'mesonpy'
  requires = ['meson-python', 'cffi']

  [project]
  name = 'squared'
  version = '0.1.0'
  requires-python = '>=3.9'
  dependencies = ['cffi']

``meson.build``:

.. code-block:: meson

  project(
      'squared',
      'c',
      version: '0.1.0',
  )

  py = import('python').find_installation(pure: false)

  install_subdir('src/squared', install_dir: py.get_install_dir())

  gen_cffi_src = find_program('gen-cffi-src')

  square_lib = static_library(
      'square',
      'src/csrc/square.c',
      include_directories: include_directories('src/csrc'),
  )
  square_dep = declare_dependency(
      link_with: square_lib,
      include_directories: include_directories('src/csrc'),
  )

  squared_ext_src = custom_target(
      'squared-cffi-src',
      command: [
          gen_cffi_src,
          'exec-python',
          '@INPUT@',
          '@OUTPUT@',
      ],
      output: '_squared.c',
      input: ['src/squared/_squared_build.py'],
  )

  py.extension_module(
      '_squared',
      squared_ext_src,
      subdir: 'squared',
      install: true,
      dependencies: [square_dep, py.dependency()],
  )

``src/squared/__init__.py``:

.. code-block:: python

   from ._squared import ffi, lib


   def squared(n):
       return lib.square(n)

``src/squared/_squared_build.py``, ``src/csrc/square.h`` and
``src/csrc/square.c`` contain the snippets shown above.

Build and install the project with any PEP 517 front-end. For
example:

.. code-block:: console

  $ python -m pip install .
  $ python -c "from squared import squared; print(squared(7))"
  49

To switch this project to ``read-sources`` mode, replace
``_squared_build.py`` with two files (``_squared.cdef.txt`` and
``_squared.csrc.c``), then change the ``custom_target`` command to:

.. code-block:: meson

  command: [
    gen_cffi_src,
    'read-sources',
    'squared._squared',
    '@INPUT0@',
    '@INPUT1@',
    '@OUTPUT@',
  ],

and list both files under ``input:``:

.. code-block:: meson

  input: ['src/squared/_squared.cdef.txt', '_squared.csrc.c']

Distributing CFFI Extensions using Setuptools
=============================================

.. _distutils-setuptools:

  You can (but don't have to) use CFFI's **Distutils** or
  **Setuptools integration** when writing a ``setup.py``.  For
  Distutils (only in out-of-line API mode; deprecated since
  Python 3.10):

  .. code-block:: python

    # setup.py (requires CFFI to be installed first)
    from distutils.core import setup

    import foo_build   # possibly with sys.path tricks to find it

    setup(
        ...,
        ext_modules=[foo_build.ffibuilder.distutils_extension()],
    )

  For Setuptools (out-of-line only, but works in ABI or API mode;
  recommended):

  .. code-block:: python

    # setup.py (with automatic dependency tracking)
    from setuptools import setup

    setup(
        ...,
        setup_requires=["cffi>=1.0.0"],
        cffi_modules=["package/foo_build.py:ffibuilder"],
        install_requires=["cffi>=1.0.0"],
    )

  Note again that the ``foo_build.py`` example contains the following
  lines, which mean that the ``ffibuilder`` is not actually compiled
  when ``package.foo_build`` is merely imported---it will be compiled
  independently by the Setuptools logic, using compilation parameters
  provided by Setuptools:

  .. code-block:: python

    if __name__ == "__main__":    # not when running with setuptools
        ffibuilder.compile(verbose=True)

* Note that some bundler tools that try to find all modules used by a
  project, like PyInstaller, will miss ``_cffi_backend`` in the
  out-of-line mode because your program contains no explicit ``import
  cffi`` or ``import _cffi_backend``.  You need to add
  ``_cffi_backend`` explicitly (as a "hidden import" in PyInstaller,
  but it can also be done more generally by adding the line ``import
  _cffi_backend`` in your main program).

Note that CFFI actually contains two different ``FFI`` classes.  The
page `Using the ffi/lib objects`_ describes the common functionality.
It is what you get in the ``from package._foo import ffi`` lines above.
On the other hand, the extended ``FFI`` class is the one you get from
``import cffi; ffi_or_ffibuilder = cffi.FFI()``.  It has the same
functionality (for in-line use), but also the extra methods described
below (to prepare the FFI).  NOTE: We use the name ``ffibuilder``
instead of ``ffi`` in the out-of-line context, when the code is about
producing a ``_foo.so`` file; this is an attempt to distinguish it
from the different ``ffi`` object that you get by later saying
``from _foo import ffi``.

.. _`Using the ffi/lib objects`: using.html

The reason for this split of functionality is that a regular program
using CFFI out-of-line does not need to import the ``cffi`` pure
Python package at all.  (Internally it still needs ``_cffi_backend``,
a C extension module that comes with CFFI; this is why CFFI is also
listed in ``install_requires=..`` above.  In the future this might be
split into a different PyPI package that only installs
``_cffi_backend``.)

Note that a few small differences do exist: notably, ``from _foo import
ffi`` returns an object of a type written in C, which does not let you
add random attributes to it (nor does it have all the
underscore-prefixed internal attributes of the Python version).
Similarly, the ``lib`` objects returned by the C version are read-only,
apart from writes to global variables.  Also, ``lib.__dict__`` does
not work before version 1.2 or if ``lib`` happens to declare a name
called ``__dict__`` (use instead ``dir(lib)``).  The same is true
for ``lib.__class__``, ``lib.__all__`` and ``lib.__name__`` added
in successive versions.
