import py
from cffi import FFI, VerificationError
from cffi.recompiler import make_py_source
from testing.udir import udir


def test_simple():
    ffi = FFI()
    ffi.cdef("int close(int); static const int BB = 42; int somevar;")
    target = udir.join('test_simple.py')
    assert make_py_source(ffi, 'test_simple', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_simple',
    _types = b'\x00\x00\x01\x0D\x00\x00\x07\x01\x00\x00\x00\x0F',
    _globals = (b'\xFF\xFF\xFF\x1FBB',42,b'\x00\x00\x00\x23close',0,b'\x00\x00\x01\x21somevar',0),
)
"""

def test_invalid_global_constant():
    ffi = FFI()
    ffi.cdef("static const int BB;")
    target = udir.join('test_invalid_global_constants.py')
    e = py.test.raises(VerificationError, make_py_source, ffi,
                       'test_invalid_global_constants', str(target))
    assert str(e.value) == (
        "ffi.dlopen() will not be able to figure out "
        "the value of constant 'BB' (only integer constants are "
        "supported, and only if their value are specified in the cdef)")

def test_invalid_dotdotdot_in_macro():
    ffi = FFI()
    ffi.cdef("#define FOO ...")
    target = udir.join('test_invalid_dotdotdot_in_macro.py')
    e = py.test.raises(VerificationError, make_py_source, ffi,
                       'test_invalid_dotdotdot_in_macro', str(target))
    assert str(e.value) == (
        "ffi.dlopen() will not be able to figure out "
        "the value of constant 'FOO' (only integer constants are "
        "supported, and only if their value are specified in the cdef)")

def test_typename():
    ffi = FFI()
    ffi.cdef("typedef int foobar_t;")
    target = udir.join('test_typename.py')
    assert make_py_source(ffi, 'test_typename', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_typename',
    _types = b'\x00\x00\x07\x01',
    _typenames = (b'\x00\x00\x00\x00foobar_t',),
)
"""

def test_enum():
    ffi = FFI()
    ffi.cdef("enum myenum_e { AA, BB, CC=-42 };")
    target = udir.join('test_enum.py')
    assert make_py_source(ffi, 'test_enum', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_enum',
    _types = b'\x00\x00\x00\x0B',
    _globals = (b'\xFF\xFF\xFF\x0BAA',0,b'\xFF\xFF\xFF\x0BBB',1,b'\xFF\xFF\xFF\x0BCC',-42),
    _enums = (b'\x00\x00\x00\x00\x00\x00\x00\x15myenum_e\x00AA,BB,CC',),
)
"""

def test_struct():
    ffi = FFI()
    ffi.cdef("struct foo_s { int a; signed char b[]; }; struct bar_s;")
    target = udir.join('test_struct.py')
    assert make_py_source(ffi, 'test_struct', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_struct',
    _types = b'\x00\x00\x07\x01\x00\x00\x03\x01\x00\x00\x01\x07\x00\x00\x00\x09\x00\x00\x01\x09',
    _struct_unions = ((b'\x00\x00\x00\x03\x00\x00\x00\x10bar_s',),(b'\x00\x00\x00\x04\x00\x00\x00\x02foo_s',b'\x00\x00\x00\x11a',b'\x00\x00\x02\x11b')),
)
"""

def test_include():
    ffi = FFI()
    ffi.cdef("#define ABC 123")
    target = udir.join('test_include.py')
    assert make_py_source(ffi, 'test_include', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_include',
    _types = b'',
    _globals = (b'\xFF\xFF\xFF\x1FABC',123,),
)
"""
    #
    ffi2 = FFI()
    ffi2.include(ffi)
    target2 = udir.join('test2_include.py')
    assert make_py_source(ffi2, 'test2_include', str(target2))
    assert target2.read() == r"""# auto-generated file
import _cffi_backend
from test_include import ffi as _ffi0

ffi = _cffi_backend.FFI(b'test2_include',
    _types = b'',
    _includes = (_ffi0,),
)
"""

def test_negative_constant():
    ffi = FFI()
    ffi.cdef("static const int BB = -42;")
    target = udir.join('test_negative_constant.py')
    assert make_py_source(ffi, 'test_negative_constant', str(target))
    assert target.read() == r"""# auto-generated file
import _cffi_backend

ffi = _cffi_backend.FFI(b'test_negative_constant',
    _types = b'',
    _globals = (b'\xFF\xFF\xFF\x1FBB',-42,),
)
"""
