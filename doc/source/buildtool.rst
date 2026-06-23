.. _buildtool_docs:

=========================================
Building and Distributing CFFI Extensions
=========================================

.. contents::

CFFI ships a command-line tool, ``gen-cffi-src``, that produces the
same output as :meth:`FFI.emit_c_code`: a ``.c`` source file ready to
be compiled into a CPython c-extension module. This tool enables
integrating with any build backend, such as `meson-python
<https://meson-python.readthedocs.io/>`_, `scikit-build-core
<https://scikit-build-core.readthedocs.io/>`_, or similar.

Installing CFFI installs the ``gen-cffi-src`` script; running ``python
-m cffi.buildtool`` invokes the same command line and behaves
identically. Use the former where a script with a Python shebang
makes more sense (e.g. cross-compiling) and use the latter when the
console script is not on PATH but a Python interpreter is.

The rest of this page uses meson-python in the examples, but any `Python build
backend`_ that lets you run a helper program during the build can
drive ``gen-cffi-src`` the same way.

The only way to use the buildtool functionality is via this command
line; the implementation inside the ``cffi`` package is private.

The implementation is based on the `cffi-buildtool`_ project by Rose Davidson
(`@inklesspen`_ on GitHub). It is included in CFFI with permission of the original
author.

.. _Python build backend: https://packaging.python.org/en/latest/guides/tool-recommendations/#build-backends-for-extension-modules
.. _cffi-buildtool: https://github.com/inklesspen/cffi-buildtool
.. _@inklesspen: https://github.com/inklesspen

The ``gen-cffi-src`` Command-line Tool
======================================

``gen-cffi-src`` has two subcommands. The first, ``exec-python`` is
most useful if you already have a Python script that sets up an FFI
definition. The second, ``read-sources`` is most useful if you are wrapping
a large API surface and want a more structured way to specify a set of FFI
definitions.

``gen-cffi-src exec-python``
----------------------------

This mode takes a Python script that dynamically defines an FFI interface and
accompanying C extension source code. The FFI definition script is the same
script you would normally run by hand -- the one the CFFI docs show under
:ref:`real-example`.

Let's say we want to create an extension module that wraps a single C function named
``square``. The ``square`` function has the following signature:

.. code-block:: C

   int square(int n);

Let's also say this function definition is exposed inside a header named
`square.h`. We could create a set of FFI bindings for this function given this
``_squared_build.py``::

  from cffi import FFI

  ffibuilder = FFI()

  ffibuilder.cdef("int square(int n);")

  ffibuilder.set_source(
      "squared._squared",
      '#include "square.h"',
  )

To generate the source code for the C extension, you would run:

.. code-block:: console

    $ gen-cffi-src exec-python _squared_build.py _squared.c

Many CFFI FFI definition scripts have an ``if __name__ == "__main__"`` section
that triggers a compilation step. This is not needed for a script run
by ``gen-cffi-src``, which does not generate compiled artifacts,
only C source code. It is up to your build-backend of choice
(e.g. meson-python) to run a C compiler and build compiled artifacts.
If the script does have such a section it is harmless: the script is
executed with ``__name__`` set to ``"cffi.buildtool"``, so the block is
skipped and an existing FFI definition script works unchanged.

If the :class:`cffi.FFI` is bound to a name other than ``ffibuilder``, pass
``--ffi-var``. To make that concrete, let's say your FFI definition script
creates an FFI object named ``make_ffi``::

    from cffi import FFI

    make_ffi = FFI()

In that case, you would pass ``--ffi-var=make_ffi`` to ``gen-cffi-src``:

.. code-block:: console

    $ gen-cffi-src exec-python --ffi-var=make_ffi _squared_build.py _squared.c

.. note::

   CFFI's setuptools integration supports passing ``libraries=``,
   ``library_dirs=``, ``include_dirs=``, and ``extra_compile_args=``
   arguments to :meth:`FFI.set_source`. When using ``gen-cffi-src``,
   these arguments are *ignored*. Link and include settings are the
   build backend's responsibility; for meson-python you would express
   them through the ``dependencies``, ``include_directories``, and
   ``c_args`` arguments of ``py.extension_module()``.

``gen-cffi-src read-sources``
-----------------------------

For larger modules, keeping the FFI definition and any necessary C
source prelude in separate files tends to be easier to work with --
you can configure your editor to treat them as plain C, and write
presubmit tooling that parses the FFI definition directly without
extracting it from a Python script.

Given ``squared.cdef.txt``:

.. code-block:: C

   int square(int n);

and ``squared.csrc.c``:

.. code-block:: C

   #include "square.h"

you would run the following command to generate the c code for a CFFI extension:

.. code-block:: console

   $ gen-cffi-src read-sources squared._squared squared.cdef.txt squared.csrc.c _squared.c

With all other details left exactly the same as the ``exec-python`` example.

The first positional argument passed to the ``read-sources`` command is the
fully qualified module name that will be embedded in the generated C source
code (equivalent to the first argument to :meth:`FFI.set_source`).


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

.. literalinclude:: ../../testing/cffi1/buildtool_examples/build_script_example/pyproject.toml
   :language: toml

``meson.build``:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/build_script_example/meson.build
   :language: meson

``src/squared/__init__.py``:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/build_script_example/src/squared/__init__.py
   :language: python

``src/squared/_squared_build.py``:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/build_script_example/src/squared/_squared_build.py
   :language: python

``src/csrc/square.h``:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/build_script_example/src/csrc/square.h
   :language: C

``src/csrc/square.c``:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/build_script_example/src/csrc/square.c
   :language: C

Build and install the project with any Python build front-end. For
example, with `pip`, in the root `squared` directory:

.. code-block:: console

  $ python -m pip install .
  $ python -c "from squared import squared; print(squared(7))"
  49

To switch this project to ``read-sources`` mode, replace
``_squared_build.py`` with two files, so that the project layout
becomes:

.. code-block:: text

  squared/
  ├── pyproject.toml
  ├── meson.build
  └── src/
      ├── squared/
      │   ├── __init__.py
      │   ├── squared.cdef.txt
      │   └── squared.csrc.c
      └── csrc/
          ├── square.h
          └── square.c

The first new file, ``squared.cdef.txt``, contains the FFI definition:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/cdef_example/src/squared/squared.cdef.txt
   :language: python

and the second, ``squared.csrc.c``, contains the C source prelude:

.. literalinclude:: ../../testing/cffi1/buildtool_examples/cdef_example/src/squared/squared.csrc.c
   :language: python

then change two spots in the ``meson.build`` file.  First, update the ``custom_target``
``command`` to call ``gen-cffi-src read-sources`` with two input arguments:

.. code-block:: meson

  command: [
    gen_cffi_src,
    'read-sources',
    'squared._squared',
    '@INPUT0@',
    '@INPUT1@',
    '@OUTPUT@',
  ],

and then list both of the FFI specification files under ``input``:

.. code-block:: meson

  input: ['src/squared/squared.cdef.txt', 'src/squared/squared.csrc.c']

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
