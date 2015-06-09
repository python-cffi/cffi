======================
What's New
======================


1.1.2
=====

* ``ffi.gc()``: fixed a race condition in multithreaded programs
  introduced in 1.1.1


1.1.1
=====

* Out-of-line mode: ``ffi.string()``, ``ffi.buffer()`` and
  ``ffi.getwinerror()`` didn't accept their arguments as keyword
  arguments, unlike their in-line mode equivalent.  (It worked in PyPy.)

* Out-of-line ABI mode: documented a restriction__ of ``ffi.dlopen()``
  when compared to the in-line mode.

* ``ffi.gc()``: when called several times with equal pointers, it was
  accidentally registering only the last destructor, or even none at
  all depending on details.  (It was correctly registering all of them
  only in PyPy, and only with the out-of-line FFIs.)

.. __: cdef.html#dlopen-note


1.1.0
=====

* Out-of-line API mode: we can now declare integer types with
  ``typedef int... foo_t;``.  The exact size and signedness of ``foo_t``
  is figured out by the compiler.

* Out-of-line API mode: we can now declare multidimensional arrays
  (as fields or as globals) with ``int n[...][...]``.  Before, only the
  outermost dimension would support the ``...`` syntax.

* Out-of-line ABI mode: we now support any constant declaration,
  instead of only integers whose value is given in the cdef.  Such "new"
  constants, i.e. either non-integers or without a value given in the
  cdef, must correspond to actual symbols in the lib.  At runtime they
  are looked up the first time we access them.  This is useful if the
  library defines ``extern const sometype somename;``.

* ``ffi.addressof(lib, "func_name")`` now returns a regular cdata object
  of type "pointer to function".  You can use it on any function from a
  library in API mode (in ABI mode, all functions are already regular
  cdata objects).  To support this, you need to recompile your cffi
  modules.

* Issue #198: in API mode, if you declare constants of a ``struct``
  type, what you saw from lib.CONSTANT was corrupted.

* Issue #196: ``ffi.set_source("package._ffi", None)`` would
  incorrectly generate the Python source to ``package._ffi.py`` instead
  of ``package/_ffi.py``.  Also fixed: in some cases, if the C file was
  in ``build/foo.c``, the .o file would be put in ``build/build/foo.o``.


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
