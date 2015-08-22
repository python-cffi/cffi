======================
What's New
======================


v1.2.1
======

* Out-of-line mode: ``int a[][...];`` can be used to declare a structure
  field or global variable which is, simultaneously, of total length
  unknown to the C compiler (the ``a[]`` part) and each element is
  itself an array of N integers, where the value of N *is* known to the
  C compiler (the ``int`` and ``[...]`` parts around it).  Similarly,
  ``int a[5][...];`` is supported (but probably less useful: remember
  that in C it means ``int (a[5])[...];``).

* PyPy: the ``lib.some_function`` objects were missing the attributes
  ``__name__``, ``__module__`` and ``__doc__`` that are expected e.g. by
  some decorators-management functions from ``functools``.

* Out-of-line API mode: you can now do ``from _example.lib import x``
  to import the name ``x`` from ``_example.lib``, even though the
  ``lib`` object is not a standard module object.  (Also works in ``from
  _example.lib import *``, but this is even more of a hack and will fail
  if ``lib`` happens to declare a name called ``__all__``.  Note that
  ``*`` excludes the global variables; only the functions and constants
  make sense to import like this.)

* ``lib.__dict__`` works again and gives you a copy of the
  dict---assuming that ``lib`` has got no symbol called precisely
  ``__dict__``.  (In general, it is safer to use ``dir(lib)``.)

* Out-of-line API mode: global variables are now fetched on demand at
  every access.  It fixes issue #212 (Windows DLL variables), and also
  allows variables that are defined as dynamic macros (like ``errno``)
  or ``__thread`` -local variables.  (This change might also tighten
  the C compiler's check on the variables' type.)

* Issue #209: dereferencing NULL pointers now raises RuntimeError
  instead of segfaulting.  Meant as a debugging aid.  The check is
  only for NULL: if you dereference random or dead pointers you might
  still get segfaults.

* Issue #152: callbacks__: added an argument ``ffi.callback(...,
  onerror=...)``.  If the main callback function raises an exception
  and ``onerror`` is provided, then ``onerror(exception, exc_value,
  traceback)`` is called.  This is similar to writing a ``try:
  except:`` in the main callback function, but in some cases (e.g. a
  signal) an exception can occur at the very start of the callback
  function---before it had time to enter the ``try: except:`` block.

* Issue #115: added ``ffi.new_allocator()``, which officializes
  support for `alternative allocators`__.

.. __: using.html#callbacks
.. __: using.html#alternative-allocators


v1.1.2
======

* ``ffi.gc()``: fixed a race condition in multithreaded programs
  introduced in 1.1.1


v1.1.1
======

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


v1.1.0
======

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


v1.0.3
======

* Same as 1.0.2, apart from doc and test fixes on some platforms.


v1.0.2
======

* Variadic C functions (ending in a "..." argument) were not supported
  in the out-of-line ABI mode.  This was a bug---there was even a
  (non-working) example__ doing exactly that!

.. __: overview.html#out-of-line-abi-level


v1.0.1
======

* ``ffi.set_source()`` crashed if passed a ``sources=[..]`` argument.
  Fixed by chrippa on pull request #60.

* Issue #193: if we use a struct between the first cdef() where it is
  declared and another cdef() where its fields are defined, then this
  definition was ignored.

* Enums were buggy if you used too many "..." in their definition.


v1.0.0
======

* The main news item is out-of-line module generation:

  * `for ABI level`_, with ``ffi.dlopen()``

  * `for API level`_, which used to be with ``ffi.verify()``, now deprecated

* (this page will list what is new from all versions from 1.0.0
  forward.)

.. _`for ABI level`: overview.html#out-of-line-abi-level
.. _`for API level`: overview.html#out-of-line-api-level
