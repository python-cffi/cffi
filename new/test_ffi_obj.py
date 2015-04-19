import py
import _cffi1_backend


def test_ffi_new():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("int *")
    p[0] = -42
    assert p[0] == -42

def test_ffi_subclass():
    class FOO(_cffi1_backend.FFI):
        def __init__(self, x):
            self.x = x
    foo = FOO(42)
    assert foo.x == 42
    p = foo.new("int *")
    assert p[0] == 0

def test_ffi_no_argument():
    py.test.raises(TypeError, _cffi1_backend.FFI, 42)

def test_ffi_cache_type():
    ffi = _cffi1_backend.FFI()
    t1 = ffi.typeof("int **")
    t2 = ffi.typeof("int *")
    assert t2.item is t1.item.item
    assert t2 is t1.item
    assert ffi.typeof("int[][10]") is ffi.typeof("int[][10]")
    assert ffi.typeof("int(*)()") is ffi.typeof("int(*)()")

def test_ffi_cache_type_globally():
    ffi1 = _cffi1_backend.FFI()
    ffi2 = _cffi1_backend.FFI()
    t1 = ffi1.typeof("int *")
    t2 = ffi2.typeof("int *")
    assert t1 is t2

def test_ffi_invalid():
    ffi = _cffi1_backend.FFI()
    # array of 10 times an "int[]" is invalid
    py.test.raises(ValueError, ffi.typeof, "int[10][]")

def test_ffi_docstrings():
    # check that all methods of the FFI class have a docstring.
    check_type = type(_cffi1_backend.FFI.new)
    for methname in dir(_cffi1_backend.FFI):
        if not methname.startswith('_'):
            method = getattr(_cffi1_backend.FFI, methname)
            if isinstance(method, check_type):
                assert method.__doc__, "method FFI.%s() has no docstring" % (
                    methname,)

def test_ffi_NULL():
    NULL = _cffi1_backend.FFI.NULL
    assert _cffi1_backend.FFI().typeof(NULL).cname == "void *"

def test_ffi_string():
    ffi = _cffi1_backend.FFI()
    p = ffi.new("char[]", "foobar\x00baz")
    assert ffi.string(p) == "foobar"

def test_ffi_errno():
    # xxx not really checking errno, just checking that we can read/write it
    ffi = _cffi1_backend.FFI()
    ffi.errno = 42
    assert ffi.errno == 42

def test_ffi_alignof():
    ffi = _cffi1_backend.FFI()
    assert ffi.alignof("int") == 4
    assert ffi.alignof("int[]") == 4
    assert ffi.alignof("int[41]") == 4
    assert ffi.alignof("short[41]") == 2
