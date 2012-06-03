ffi
===

Foreign Function Interface for Python.


Initial motivation
------------------

http://mail.python.org/pipermail/pypy-dev/2012-May/009915.html


Current status
--------------

* works as a ctypes replacement
* can use internally either ctypes or a C extension module


Next steps
----------

the verify() step, which should handle:
 * completing "...;" structs
 * checking the other structs, and the arguments to functions, using the real C compiler
 * simple "#define FOO value" macros
 * macros of the kind "#define funcname otherfuncname"
 * more complicated macros "#define foo(a, b, c) ..."
 * checking and correcting the value of the enum {} declarations
 * probably also fixing the array lengths, e.g. declared as a field "int foo[...];"

generating C extensions:
 * this is needed anyway to call macros
 * faster, libffi-free way to call C code
 * partial blockers: callbacks (probably still use libffi)

_ffi backend for PyPy
