import sys
from cffi import FFI
from cffi import recompiler, ffiplatform
from testing.udir import udir


def setup_module(mod):
    SRC = """
    #define FOOBAR (-42)
    int add42(int x) { return x + 42; }
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
