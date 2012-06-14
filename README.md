cffi
====

Foreign Function Interface for Python calling C code. The aim of this project
is to provide a convinient and reliable way of calling C code from Python.
The interface is based on `luajit FFI`_ and follows few principles:

* Able to call C from Python without introducing a third language
  (unlike Cython or SWIG)

* Keep all the python-related logic in Python instead of C (unlike CPython
  native C extensions)

* Be complete and work on the level of API (unlike ctypes)

.. _`luajit FFI`: http://luajit.org/ext_ffi.html

Simple example
--------------

xxx

Contact
-------

Mailing list: https://groups.google.com/forum/#!forum/python-cffi


Initial motivation
------------------

http://mail.python.org/pipermail/pypy-dev/2012-May/009915.html
