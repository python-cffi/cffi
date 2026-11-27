import io

from cffi import FFI, recompiler
from testing.cffi0.test_parsing import FakeBackend


def _emit_c_source(cdef_src, module_name="pkg.myext", preamble=""):
    ffi = FFI(backend=FakeBackend())
    ffi.cdef(cdef_src)
    recomp = recompiler.Recompiler(ffi, module_name)
    recomp.collect_type_table()
    recomp.collect_step_tables()
    buf = io.StringIO()
    recomp.write_source_to_f(buf, preamble)
    return buf.getvalue()


def test_pypy_windows_pyinit_exported_on_mingw():
    c_src = _emit_c_source("int foo(int);", module_name="pkg.myext")
    pypy_block = c_src.split("#ifdef PYPY_VERSION", 1)[1].split("#else", 1)[0]
    assert "_cffi_pypyinit_myext" in pypy_block
    assert "#  ifdef _WIN32" in pypy_block
    assert "#  ifdef _MSC_VER" not in pypy_block
    assert "PyInit_myext(void) { return NULL; }" in pypy_block
