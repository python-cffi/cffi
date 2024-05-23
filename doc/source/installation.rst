=======================================================
Installation and Status
=======================================================

Quick installation for CPython (cffi is distributed with PyPy):

* ``pip install cffi``

* or get the source code via the `Python Package Index`__.

.. __: http://pypi.python.org/pypi/cffi

In more details:

This code has been developed on Linux, but should work on any POSIX
platform as well as on Windows 32 and 64.  (It relies occasionally on
libffi, so it depends on libffi being bug-free; this may not be fully
the case on some of the more exotic platforms.)

CFFI is tested with CPython 3.8-3.13.

The core speed of CFFI is better than ctypes, with import times being
either lower if you use the post-1.0 features, or much higher if you
don't.  The wrapper Python code you typically need to write around the
raw CFFI interface slows things down on CPython, but not unreasonably
so.  On PyPy, this wrapper code has a minimal impact thanks to the JIT
compiler.  This makes CFFI the recommended way to interface with C
libraries on PyPy.

Requirements:

* CPython 3.8+, or PyPy (PyPy 2.0 for the earliest
  versions of CFFI; or PyPy 2.6 for CFFI 1.0).

* in some cases you need to be able to compile C extension modules.
  On non-Windows platforms, this usually means installing the package
  ``python-dev``.  Refer to the appropriate docs for your OS.

* on CPython, on non-Windows platforms, you also need to install
  ``libffi-dev`` in order to compile CFFI itself.

* pycparser >= 2.06: https://github.com/eliben/pycparser (automatically
  tracked by ``pip install cffi``).

* `pytest`_ is needed to run the tests of CFFI itself.

.. _`pytest`: http://pypi.python.org/pypi/pytest

Download and Installation:

* https://pypi.python.org/pypi/cffi

* Or grab the most current version from `GitHub`_:
  ``git clone https://github.com/python-cffi/cffi``

* running the tests: ``pytest  c/  testing/`` (if you didn't
  install cffi yet, you need first ``python setup_base.py build_ext -f
  -i``)

.. _`GitHub project home`: https://github.com/python-cffi/cffi

Demos:

* The `demo`_ directory contains a number of small and large demos
  of using ``cffi``.

* The documentation below might be sketchy on details; for now the
  ultimate reference is given by the tests, notably
  `testing/cffi1/test_verify1.py`_ and `testing/cffi0/backend_tests.py`_.

.. _`demo`: https://github.com/python-cffi/cffi/blob/main/demo
.. _`testing/cffi1/test_verify1.py`: https://github.com/python-cffi/cffi/blob/main/testing/cffi1/test_verify1.py
.. _`testing/cffi0/backend_tests.py`: https://github.com/python-cffi/cffi/blob/main/testing/cffi0/backend_tests.py


Platform-specific instructions
------------------------------

``libffi`` is notoriously messy to install and use --- to the point that
CPython includes its own copy to avoid relying on external packages.
CFFI does the same for Windows, but not for other platforms (which should
have their own working libffi's).
Modern Linuxes work out of the box thanks to ``pkg-config``.  Here are some
(user-supplied) instructions for other platforms.


MacOS X
+++++++

**Homebrew** (Thanks David Griffin and Mark Keller for this)

1) Install homebrew: http://brew.sh

2) Run the following commands in a terminal

::

    brew install pkg-config libffi
    PKG_CONFIG_PATH=$(brew --prefix libffi)/lib/pkgconfig pip install --no-binary cffi cffi

(the ``--no-binary cffi`` might be needed or not.)


Alternatively, **on OS/X 10.6** (Thanks Juraj Sukop for this)

For building libffi you can use the default install path, but then, in
``setup.py`` you need to change::

    include_dirs = []

to::

    include_dirs = ['/usr/local/lib/libffi-3.0.11/include']

Then running ``python setup.py build`` complains about "fatal error: error writing to -: Broken pipe", which can be fixed by running::

    ARCHFLAGS="-arch i386 -arch x86_64" python setup.py build

as described here_.

.. _here: http://superuser.com/questions/259278/python-2-6-1-pycrypto-2-3-pypi-package-broken-pipe-during-build


Windows (32/64-bit)
+++++++++++++++++++

Win32 and Win64 work and are tested at least each official release.

The recommended C compiler compatible with Python 2.7 is this one:
http://www.microsoft.com/en-us/download/details.aspx?id=44266
There is a known problem with distutils on Python 2.7, as
explained in https://bugs.python.org/issue23246, and the same
problem applies whenever you want to run compile() to build a dll with
this specific compiler suite download.
``import setuptools`` might help, but YMMV

More generally, the solution that should always work is to download the
sources of CFFI (instead of a prebuilt binary) and make sure that you
build it with the same version of Python that will use it.
For example, with virtualenv:

* ``virtualenv ~/venv``

* ``cd ~/path/to/sources/of/cffi``

* ``~/venv/bin/python setup.py build --force`` # forcing a rebuild to
  make sure

* ``~/venv/bin/python setup.py install``

This will compile and install CFFI in this virtualenv, using the
Python from this virtualenv.


NetBSD
++++++

You need to make sure you have an up-to-date version of libffi, which
fixes some bugs.
