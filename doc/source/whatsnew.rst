======================
What's New
======================



1.0.3
=====

* Same as 1.0.2, apart from doc and test fixes on some platforms.


1.0.2
=====

* Variadic C functions (ending in a "..." argument) were not supported
  in the out-of-line ABI mode.  This was a bug---there was even a
  (non-working) example__ doing exactly that!

.. __: overview.html#out-of-line-abi-level


1.0.1
=====

* ``ffi.set_source()`` crashed if passed a ``sources=[..]`` argument.
  Fixed by chrippa on pull request #60.

* Issue #193: if we use a struct between the first cdef() where it is
  declared and another cdef() where its fields are defined, then this
  definition was ignored.

* Enums were buggy if you used too many "..." in their definition.


1.0.0
=====

* The main news item is out-of-line module generation:

  * `for ABI level`_, with ``ffi.dlopen()``

  * `for API level`_, which used to be with ``ffi.verify()``, now deprecated

* (this page will list what is new from all versions from 1.0.0
  forward.)

.. _`for ABI level`: overview.html#out-of-line-abi-level
.. _`for API level`: overview.html#out-of-line-api-level
