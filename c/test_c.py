import py
import _ffi_backend


def size_of_int():
    BInt = _ffi_backend.new_primitive_type(None, "int")
    return _ffi_backend.sizeof_type(BInt)

def size_of_ptr():
    BInt = _ffi_backend.new_primitive_type(None, "int")
    BPtr = _ffi_backend.new_pointer_type(None, BInt)
    return _ffi_backend.sizeof_type(BPtr)


def test_load_library():
    x = _ffi_backend.load_library("libc.so.6")     # Linux only
    assert repr(x).startswith("<_ffi_backend.Library object at 0x")

def test_nonstandard_integer_types():
    d = _ffi_backend.nonstandard_integer_types()
    assert type(d) is dict
    assert 'char' not in d
    assert d['size_t'] in (0x1004, 0x1008)
    assert d['size_t'] == d['ssize_t'] + 0x1000

def test_new_primitive_type():
    py.test.raises(KeyError, _ffi_backend.new_primitive_type, None, "foo")
    p = _ffi_backend.new_primitive_type(None, "signed char")
    assert repr(p) == "<ctype 'signed char'>"

def test_cast_to_signed_char():
    p = _ffi_backend.new_primitive_type(None, "signed char")
    x = _ffi_backend.cast(p, -65 + 17*256)
    assert repr(x) == "<cdata 'signed char'>"
    assert repr(type(x)) == "<type '_ffi_backend.CData'>"
    assert int(x) == -65
    x = _ffi_backend.cast(p, -66 + (1<<199)*256)
    assert repr(x) == "<cdata 'signed char'>"
    assert int(x) == -66
    assert (x == _ffi_backend.cast(p, -66)) is False
    assert (x != _ffi_backend.cast(p, -66)) is True
    q = _ffi_backend.new_primitive_type(None, "short")
    assert (x == _ffi_backend.cast(q, -66)) is False
    assert (x != _ffi_backend.cast(q, -66)) is True
    assert hash(x) == hash(_ffi_backend.cast(p, -66))

def test_sizeof_type():
    py.test.raises(TypeError, _ffi_backend.sizeof_type, 42.5)
    p = _ffi_backend.new_primitive_type(None, "short")
    assert _ffi_backend.sizeof_type(p) == 2

def test_integer_types():
    for name in ['signed char', 'short', 'int', 'long', 'long long']:
        p = _ffi_backend.new_primitive_type(None, name)
        size = _ffi_backend.sizeof_type(p)
        min = -(1 << (8*size-1))
        max = (1 << (8*size-1)) - 1
        assert int(_ffi_backend.cast(p, min)) == min
        assert int(_ffi_backend.cast(p, max)) == max
        assert int(_ffi_backend.cast(p, min - 1)) == max
        assert int(_ffi_backend.cast(p, max + 1)) == min
        assert long(_ffi_backend.cast(p, min - 1)) == max
    for name in ['char', 'short', 'int', 'long', 'long long']:
        p = _ffi_backend.new_primitive_type(None, 'unsigned ' + name)
        size = _ffi_backend.sizeof_type(p)
        max = (1 << (8*size)) - 1
        assert int(_ffi_backend.cast(p, 0)) == 0
        assert int(_ffi_backend.cast(p, max)) == max
        assert int(_ffi_backend.cast(p, -1)) == max
        assert int(_ffi_backend.cast(p, max + 1)) == 0
        assert long(_ffi_backend.cast(p, -1)) == max

def test_no_float_on_int_types():
    p = _ffi_backend.new_primitive_type(None, 'long')
    py.test.raises(TypeError, float, _ffi_backend.cast(p, 42))

def test_float_types():
    INF = 1E200 * 1E200
    for name in ["float", "double"]:
        p = _ffi_backend.new_primitive_type(None, name)
        assert bool(_ffi_backend.cast(p, 0))
        assert bool(_ffi_backend.cast(p, INF))
        assert bool(_ffi_backend.cast(p, -INF))
        assert int(_ffi_backend.cast(p, -150)) == -150
        assert int(_ffi_backend.cast(p, 61.91)) == 61
        assert long(_ffi_backend.cast(p, 61.91)) == 61L
        assert type(int(_ffi_backend.cast(p, 61.91))) is int
        assert type(int(_ffi_backend.cast(p, 1E22))) is long
        assert type(long(_ffi_backend.cast(p, 61.91))) is long
        assert type(long(_ffi_backend.cast(p, 1E22))) is long
        py.test.raises(OverflowError, int, _ffi_backend.cast(p, INF))
        py.test.raises(OverflowError, int, _ffi_backend.cast(p, -INF))
        assert float(_ffi_backend.cast(p, 1.25)) == 1.25
        assert float(_ffi_backend.cast(p, INF)) == INF
        assert float(_ffi_backend.cast(p, -INF)) == -INF
        if name == "float":
            assert float(_ffi_backend.cast(p, 1.1)) != 1.1     # rounding error
            assert float(_ffi_backend.cast(p, 1E200)) == INF   # limited range

        assert _ffi_backend.cast(p, -1.1) != _ffi_backend.cast(p, -1.1)
        assert (hash(_ffi_backend.cast(p, -0.0)) ==
                hash(_ffi_backend.cast(p, 0.0)))
        assert repr(float(_ffi_backend.cast(p, -0.0))) == '-0.0'

def test_character_type():
    p = _ffi_backend.new_primitive_type(None, "char")
    assert bool(_ffi_backend.cast(p, '\x00'))
    assert _ffi_backend.cast(p, '\x00') != _ffi_backend.cast(p, -17*256)
    assert int(_ffi_backend.cast(p, 'A')) == 65
    assert long(_ffi_backend.cast(p, 'A')) == 65L
    assert type(int(_ffi_backend.cast(p, 'A'))) is int
    assert type(long(_ffi_backend.cast(p, 'A'))) is long
    assert str(_ffi_backend.cast(p, 'A')) == 'A'

def test_pointer_type():
    p = _ffi_backend.new_primitive_type(None, "int")
    assert repr(p) == "<ctype 'int'>"
    p = _ffi_backend.new_pointer_type(None, p)
    assert repr(p) == "<ctype 'int *'>"
    p = _ffi_backend.new_pointer_type(None, p)
    assert repr(p) == "<ctype 'int * *'>"
    p = _ffi_backend.new_pointer_type(None, p)
    assert repr(p) == "<ctype 'int * * *'>"

def test_pointer_to_int():
    BInt = _ffi_backend.new_primitive_type(None, "int")
    py.test.raises(TypeError, _ffi_backend.new, BInt, None)
    BPtr = _ffi_backend.new_pointer_type(None, BInt)
    p = _ffi_backend.new(BPtr, None)
    assert repr(p) == "<cdata 'int *' owning %d bytes>" % size_of_int()
    p = _ffi_backend.new(BPtr, 5000)
    assert repr(p) == "<cdata 'int *' owning %d bytes>" % size_of_int()
    q = _ffi_backend.cast(BPtr, p)
    assert repr(q) == "<cdata 'int *'>"

def test_pointer_to_pointer():
    BInt = _ffi_backend.new_primitive_type(None, "int")
    BPtr = _ffi_backend.new_pointer_type(None, BInt)
    BPtrPtr = _ffi_backend.new_pointer_type(None, BPtr)
    p = _ffi_backend.new(BPtrPtr, None)
    assert repr(p) == "<cdata 'int * *' owning %d bytes>" % size_of_ptr()

def test_reading_pointer_to_int():
    BInt = _ffi_backend.new_primitive_type(None, "int")
    BPtr = _ffi_backend.new_pointer_type(None, BInt)
    p = _ffi_backend.new(BPtr, None)
    assert p[0] == 0
    p = _ffi_backend.new(BPtr, 5000)
    assert p[0] == 5000
    py.test.raises(IndexError, "p[1]")
    py.test.raises(IndexError, "p[-1]")

def test_reading_pointer_to_float():
    BFloat = _ffi_backend.new_primitive_type(None, "float")
    py.test.raises(TypeError, _ffi_backend.new, BFloat, None)
    BPtr = _ffi_backend.new_pointer_type(None, BFloat)
    p = _ffi_backend.new(BPtr, None)
    assert p[0] == 0.0 and type(p[0]) is float
    p = _ffi_backend.new(BPtr, 1.25)
    assert p[0] == 1.25 and type(p[0]) is float
    p = _ffi_backend.new(BPtr, 1.1)
    assert p[0] != 1.1 and abs(p[0] - 1.1) < 1E-5   # rounding errors

def test_reading_pointer_to_char():
    BChar = _ffi_backend.new_primitive_type(None, "char")
    py.test.raises(TypeError, _ffi_backend.new, BChar, None)
    BPtr = _ffi_backend.new_pointer_type(None, BChar)
    p = _ffi_backend.new(BPtr, None)
    assert p[0] == '\x00'
    p = _ffi_backend.new(BPtr, 'A')
    assert p[0] == 'A'
    py.test.raises(TypeError, _ffi_backend.new, BPtr, 65)
    py.test.raises(TypeError, _ffi_backend.new, BPtr, "foo")

def test_hash_differences():
    BChar = _ffi_backend.new_primitive_type(None, "char")
    BInt = _ffi_backend.new_primitive_type(None, "int")
    BFloat = _ffi_backend.new_primitive_type(None, "float")
    assert (hash(_ffi_backend.cast(BChar, 'A')) !=
            hash(_ffi_backend.cast(BInt, 65)))
    assert hash(_ffi_backend.cast(BFloat, 65)) != hash(65.0)
