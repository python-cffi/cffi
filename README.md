cffi
====

Foreign Function Interface for Python calling C code.

Mailing list: https://groups.google.com/forum/#!forum/python-cffi


Initial motivation
------------------

http://mail.python.org/pipermail/pypy-dev/2012-May/009915.html


Current status
--------------

* works as a ctypes replacement
* can use internally either ctypes or a C extension module


Next steps
----------

the verify() step, which is missing:

* global variables

* typedef ... some_integer_type;


_ffi backend for PyPy
