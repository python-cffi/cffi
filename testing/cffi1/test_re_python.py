import sys
import py
from cffi import FFI
from cffi import recompiler, ffiplatform
from testing.udir import udir


def setup_module(mod):
    SRC = """
    #define FOOBAR (-42)
    int add42(int x) { return x + 42; }
    struct foo_s;
    struct bar_s { int x; signed char a[]; };
    """
    tmpdir = udir.join('test_re_python')
    tmpdir.ensure(dir=1)
    c_file = tmpdir.join('_test_re_python.c')
    c_file.write(SRC)
    ext = ffiplatform.get_extension(str(c_file), '_test_re_python')
    outputfilename = ffiplatform.compile(str(tmpdir), ext)
    mod.extmod = outputfilename
    #
    ffi = FFI()
    ffi.cdef("""
    #define FOOBAR -42
    int add42(int);
    struct foo_s;
    struct bar_s { int x; signed char a[]; };
    """)
    ffi.set_source('re_python_pysrc', None)
    ffi.emit_python_code(str(tmpdir.join('re_python_pysrc.py')))
    #
    sys.path.insert(0, str(tmpdir))


def test_constant():
    from re_python_pysrc import ffi
    assert ffi.integer_const('FOOBAR') == -42

def test_function():
    from re_python_pysrc import ffi
    lib = ffi.dlopen(extmod)
    assert lib.add42(-10) == 32

def test_constant_via_lib():
    from re_python_pysrc import ffi
    lib = ffi.dlopen(extmod)
    assert lib.FOOBAR == -42

def test_opaque_struct():
    from re_python_pysrc import ffi
    ffi.cast("struct foo_s *", 0)
    py.test.raises(TypeError, ffi.new, "struct foo_s *")

def test_nonopaque_struct():
    from re_python_pysrc import ffi
    p = ffi.new("struct bar_s *", [5, "foobar"])
    assert p.x == 5
    assert p.a[0] == ord('f')
    assert p.a[5] == ord('r')
