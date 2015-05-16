import sys
import py
from cffi import FFI
from cffi import recompiler, ffiplatform
from testing.udir import udir


def setup_module(mod):
    SRC = """
    #define FOOBAR (-42)
    static const int FOOBAZ = -43;
    int add42(int x) { return x + 42; }
    struct foo_s;
    typedef struct bar_s { int x; signed char a[]; } bar_t;
    enum foo_e { AA, BB, CC };
    """
    tmpdir = udir.join('test_re_python')
    tmpdir.ensure(dir=1)
    c_file = tmpdir.join('_test_re_python.c')
    c_file.write(SRC)
    ext = ffiplatform.get_extension(str(c_file), '_test_re_python')
    outputfilename = ffiplatform.compile(str(tmpdir), ext)
    mod.extmod = outputfilename
    mod.tmpdir = tmpdir
    #
    ffi = FFI()
    ffi.cdef("""
    #define FOOBAR -42
    static const int FOOBAZ = -43;
    int add42(int);
    struct foo_s;
    typedef struct bar_s { int x; signed char a[]; } bar_t;
    enum foo_e { AA, BB, CC };
    """)
    ffi.set_source('re_python_pysrc', None)
    ffi.emit_python_code(str(tmpdir.join('re_python_pysrc.py')))
    mod.original_ffi = ffi
    #
    sys.path.insert(0, str(tmpdir))


def test_constant():
    from re_python_pysrc import ffi
    assert ffi.integer_const('FOOBAR') == -42
    assert ffi.integer_const('FOOBAZ') == -43

def test_function():
    from re_python_pysrc import ffi
    lib = ffi.dlopen(extmod)
    assert lib.add42(-10) == 32

def test_constant_via_lib():
    from re_python_pysrc import ffi
    lib = ffi.dlopen(extmod)
    assert lib.FOOBAR == -42
    assert lib.FOOBAZ == -43

def test_opaque_struct():
    from re_python_pysrc import ffi
    ffi.cast("struct foo_s *", 0)
    py.test.raises(TypeError, ffi.new, "struct foo_s *")

def test_nonopaque_struct():
    from re_python_pysrc import ffi
    for p in [ffi.new("struct bar_s *", [5, "foobar"]),
              ffi.new("bar_t *", [5, "foobar"])]:
        assert p.x == 5
        assert p.a[0] == ord('f')
        assert p.a[5] == ord('r')

def test_enum():
    from re_python_pysrc import ffi
    assert ffi.integer_const("BB") == 1
    e = ffi.cast("enum foo_e", 2)
    assert ffi.string(e) == "CC"

def test_include_1():
    ffi2 = FFI()
    ffi2.cdef("static const int k2 = 121212;")
    ffi2.include(original_ffi)
    assert 'macro FOOBAR' in original_ffi._parser._declarations
    assert 'macro FOOBAZ' in original_ffi._parser._declarations
    ffi2.set_source('re_python_pysrc', None)
    ffi2.emit_python_code(str(tmpdir.join('_re_include_1.py')))
    #
    from _re_include_1 import ffi
    assert ffi.integer_const('FOOBAR') == -42
    assert ffi.integer_const('FOOBAZ') == -43
    assert ffi.integer_const('k2') == 121212
    lib = ffi.dlopen(None)
    assert lib.FOOBAR == -42
    assert lib.FOOBAZ == -43
    assert lib.k2 == 121212
