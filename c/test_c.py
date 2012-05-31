import py, sys
from _ffi_backend import *
from _ffi_backend import _getfields


def size_of_int():
    BInt = new_primitive_type("int")
    return sizeof_type(BInt)

def size_of_ptr():
    BInt = new_primitive_type("int")
    BPtr = new_pointer_type(BInt)
    return sizeof_type(BPtr)


def test_load_library():
    x = load_library("libc.so.6")     # Linux only
    assert repr(x).startswith("<_ffi_backend.Library object at 0x")

def test_nonstandard_integer_types():
    d = nonstandard_integer_types()
    assert type(d) is dict
    assert 'char' not in d
    assert d['size_t'] in (0x1004, 0x1008)
    assert d['size_t'] == d['ssize_t'] + 0x1000

def test_new_primitive_type():
    py.test.raises(KeyError, new_primitive_type, "foo")
    p = new_primitive_type("signed char")
    assert repr(p) == "<ctype 'signed char'>"

def test_cast_to_signed_char():
    p = new_primitive_type("signed char")
    x = cast(p, -65 + 17*256)
    assert repr(x) == "<cdata 'signed char'>"
    assert repr(type(x)) == "<type '_ffi_backend.CData'>"
    assert int(x) == -65
    x = cast(p, -66 + (1<<199)*256)
    assert repr(x) == "<cdata 'signed char'>"
    assert int(x) == -66
    assert (x == cast(p, -66)) is False
    assert (x != cast(p, -66)) is True
    q = new_primitive_type("short")
    assert (x == cast(q, -66)) is False
    assert (x != cast(q, -66)) is True

def test_sizeof_type():
    py.test.raises(TypeError, sizeof_type, 42.5)
    p = new_primitive_type("short")
    assert sizeof_type(p) == 2

def test_integer_types():
    for name in ['signed char', 'short', 'int', 'long', 'long long']:
        p = new_primitive_type(name)
        size = sizeof_type(p)
        min = -(1 << (8*size-1))
        max = (1 << (8*size-1)) - 1
        assert int(cast(p, min)) == min
        assert int(cast(p, max)) == max
        assert int(cast(p, min - 1)) == max
        assert int(cast(p, max + 1)) == min
        assert long(cast(p, min - 1)) == max
    for name in ['char', 'short', 'int', 'long', 'long long']:
        p = new_primitive_type('unsigned ' + name)
        size = sizeof_type(p)
        max = (1 << (8*size)) - 1
        assert int(cast(p, 0)) == 0
        assert int(cast(p, max)) == max
        assert int(cast(p, -1)) == max
        assert int(cast(p, max + 1)) == 0
        assert long(cast(p, -1)) == max

def test_no_float_on_int_types():
    p = new_primitive_type('long')
    py.test.raises(TypeError, float, cast(p, 42))

def test_float_types():
    INF = 1E200 * 1E200
    for name in ["float", "double"]:
        p = new_primitive_type(name)
        assert bool(cast(p, 0))
        assert bool(cast(p, INF))
        assert bool(cast(p, -INF))
        assert int(cast(p, -150)) == -150
        assert int(cast(p, 61.91)) == 61
        assert long(cast(p, 61.91)) == 61L
        assert type(int(cast(p, 61.91))) is int
        assert type(int(cast(p, 1E22))) is long
        assert type(long(cast(p, 61.91))) is long
        assert type(long(cast(p, 1E22))) is long
        py.test.raises(OverflowError, int, cast(p, INF))
        py.test.raises(OverflowError, int, cast(p, -INF))
        assert float(cast(p, 1.25)) == 1.25
        assert float(cast(p, INF)) == INF
        assert float(cast(p, -INF)) == -INF
        if name == "float":
            assert float(cast(p, 1.1)) != 1.1     # rounding error
            assert float(cast(p, 1E200)) == INF   # limited range

        assert cast(p, -1.1) != cast(p, -1.1)
        assert repr(float(cast(p, -0.0))) == '-0.0'

def test_character_type():
    p = new_primitive_type("char")
    assert bool(cast(p, '\x00'))
    assert cast(p, '\x00') != cast(p, -17*256)
    assert int(cast(p, 'A')) == 65
    assert long(cast(p, 'A')) == 65L
    assert type(int(cast(p, 'A'))) is int
    assert type(long(cast(p, 'A'))) is long
    assert str(cast(p, 'A')) == 'A'

def test_pointer_type():
    p = new_primitive_type("int")
    assert repr(p) == "<ctype 'int'>"
    p = new_pointer_type(p)
    assert repr(p) == "<ctype 'int *'>"
    p = new_pointer_type(p)
    assert repr(p) == "<ctype 'int * *'>"
    p = new_pointer_type(p)
    assert repr(p) == "<ctype 'int * * *'>"

def test_pointer_to_int():
    BInt = new_primitive_type("int")
    py.test.raises(TypeError, new, BInt, None)
    BPtr = new_pointer_type(BInt)
    p = new(BPtr, None)
    assert repr(p) == "<cdata 'int *' owning %d bytes>" % size_of_int()
    p = new(BPtr, 5000)
    assert repr(p) == "<cdata 'int *' owning %d bytes>" % size_of_int()
    q = cast(BPtr, p)
    assert repr(q) == "<cdata 'int *'>"
    assert p == q
    assert hash(p) == hash(q)

def test_pointer_to_pointer():
    BInt = new_primitive_type("int")
    BPtr = new_pointer_type(BInt)
    BPtrPtr = new_pointer_type(BPtr)
    p = new(BPtrPtr, None)
    assert repr(p) == "<cdata 'int * *' owning %d bytes>" % size_of_ptr()

def test_reading_pointer_to_int():
    BInt = new_primitive_type("int")
    BPtr = new_pointer_type(BInt)
    p = new(BPtr, None)
    assert p[0] == 0
    p = new(BPtr, 5000)
    assert p[0] == 5000
    py.test.raises(IndexError, "p[1]")
    py.test.raises(IndexError, "p[-1]")

def test_reading_pointer_to_float():
    BFloat = new_primitive_type("float")
    py.test.raises(TypeError, new, BFloat, None)
    BPtr = new_pointer_type(BFloat)
    p = new(BPtr, None)
    assert p[0] == 0.0 and type(p[0]) is float
    p = new(BPtr, 1.25)
    assert p[0] == 1.25 and type(p[0]) is float
    p = new(BPtr, 1.1)
    assert p[0] != 1.1 and abs(p[0] - 1.1) < 1E-5   # rounding errors

def test_reading_pointer_to_char():
    BChar = new_primitive_type("char")
    py.test.raises(TypeError, new, BChar, None)
    BPtr = new_pointer_type(BChar)
    p = new(BPtr, None)
    assert p[0] == '\x00'
    p = new(BPtr, 'A')
    assert p[0] == 'A'
    py.test.raises(TypeError, new, BPtr, 65)
    py.test.raises(TypeError, new, BPtr, "foo")

def test_hash_differences():
    BChar = new_primitive_type("char")
    BInt = new_primitive_type("int")
    BFloat = new_primitive_type("float")
    assert (hash(cast(BChar, 'A')) !=
            hash(cast(BInt, 65)))
    assert hash(cast(BFloat, 65)) != hash(65.0)

def test_array_type():
    p = new_primitive_type("int")
    assert repr(p) == "<ctype 'int'>"
    #
    py.test.raises(TypeError, new_array_type, new_pointer_type(p), "foo")
    py.test.raises(ValueError, new_array_type, new_pointer_type(p), -42)
    #
    p1 = new_array_type(new_pointer_type(p), None)
    assert repr(p1) == "<ctype 'int[]'>"
    py.test.raises(ValueError, new_array_type, new_pointer_type(p1), 42)
    #
    p1 = new_array_type(new_pointer_type(p), 42)
    p2 = new_array_type(new_pointer_type(p1), 25)
    assert repr(p2) == "<ctype 'int[25][42]'>"
    p2 = new_array_type(new_pointer_type(p1), None)
    assert repr(p2) == "<ctype 'int[][42]'>"
    #
    py.test.raises(OverflowError,
                   new_array_type, new_pointer_type(p), sys.maxint+1)
    py.test.raises(OverflowError,
                   new_array_type, new_pointer_type(p), sys.maxint // 3)

def test_array_instance():
    LENGTH = 14242
    p = new_primitive_type("int")
    p1 = new_array_type(new_pointer_type(p), LENGTH)
    a = new(p1, None)
    assert repr(a) == "<cdata 'int[%d]' owning %d bytes>" % (
        LENGTH, LENGTH * size_of_int())
    assert len(a) == LENGTH
    for i in range(LENGTH):
        assert a[i] == 0
    py.test.raises(IndexError, "a[LENGTH]")
    py.test.raises(IndexError, "a[-1]")
    for i in range(LENGTH):
        a[i] = i * i + 1
    for i in range(LENGTH):
        assert a[i] == i * i + 1
    e = py.test.raises(IndexError, "a[LENGTH+100] = 500")
    assert ('(expected %d < %d)' % (LENGTH+100, LENGTH)) in str(e.value)

def test_array_of_unknown_length_instance():
    p = new_primitive_type("int")
    p1 = new_array_type(new_pointer_type(p), None)
    py.test.raises(TypeError, new, p1, None)
    py.test.raises(ValueError, new, p1, -42)
    a = new(p1, 42)
    assert len(a) == 42
    for i in range(42):
        a[i] -= i
    for i in range(42):
        assert a[i] == -i
    py.test.raises(IndexError, "a[42]")
    py.test.raises(IndexError, "a[-1]")
    py.test.raises(IndexError, "a[42] = 123")
    py.test.raises(IndexError, "a[-1] = 456")

def test_array_of_unknown_length_instance_with_initializer():
    p = new_primitive_type("int")
    p1 = new_array_type(new_pointer_type(p), None)
    a = new(p1, range(42))
    assert len(a) == 42
    a = new(p1, tuple(range(142)))
    assert len(a) == 142

def test_array_initializer():
    p = new_primitive_type("int")
    p1 = new_array_type(new_pointer_type(p), None)
    a = new(p1, range(100, 142))
    for i in range(42):
        assert a[i] == 100 + i
    #
    p2 = new_array_type(new_pointer_type(p), 43)
    a = new(p2, tuple(range(100, 142)))
    for i in range(42):
        assert a[i] == 100 + i
    assert a[42] == 0      # extra uninitialized item

def test_cast_primitive_from_cdata():
    p = new_primitive_type("int")
    n = cast(p, cast(p, -42))
    assert int(n) == -42
    #
    p = new_primitive_type("unsigned int")
    n = cast(p, cast(p, 42))
    assert int(n) == 42
    #
    p = new_primitive_type("long long")
    n = cast(p, cast(p, -(1<<60)))
    assert int(n) == -(1<<60)
    #
    p = new_primitive_type("unsigned long long")
    n = cast(p, cast(p, 1<<63))
    assert int(n) == 1<<63
    #
    p = new_primitive_type("float")
    n = cast(p, cast(p, 42.5))
    assert float(n) == 42.5
    #
    p = new_primitive_type("char")
    n = cast(p, cast(p, "A"))
    assert str(n) == "A"

def test_new_primitive_from_cdata():
    p = new_primitive_type("int")
    p1 = new_pointer_type(p)
    n = new(p1, cast(p, -42))
    assert n[0] == -42
    #
    p = new_primitive_type("unsigned int")
    p1 = new_pointer_type(p)
    n = new(p1, cast(p, 42))
    assert n[0] == 42
    #
    p = new_primitive_type("float")
    p1 = new_pointer_type(p)
    n = new(p1, cast(p, 42.5))
    assert n[0] == 42.5
    #
    p = new_primitive_type("char")
    p1 = new_pointer_type(p)
    n = new(p1, cast(p, "A"))
    assert n[0] == "A"

def test_alignof():
    BInt = new_primitive_type("int")
    assert alignof(BInt) == sizeof_type(BInt)
    BPtr = new_pointer_type(BInt)
    assert alignof(BPtr) == sizeof_type(BPtr)
    BArray = new_array_type(BPtr, None)
    assert alignof(BArray) == alignof(BInt)

def test_new_struct_type():
    BStruct = new_struct_type("foo")
    assert repr(BStruct) == "<ctype 'struct foo'>"
    BPtr = new_pointer_type(BStruct)
    assert repr(BPtr) == "<ctype 'struct foo *'>"

def test_new_union_type():
    BUnion = new_union_type("foo")
    assert repr(BUnion) == "<ctype 'union foo'>"
    BPtr = new_pointer_type(BUnion)
    assert repr(BPtr) == "<ctype 'union foo *'>"

def test_complete_struct():
    BLong = new_primitive_type("long")
    BChar = new_primitive_type("char")
    BShort = new_primitive_type("short")
    BStruct = new_struct_type("foo")
    assert _getfields(BStruct) is None
    complete_struct_or_union(BStruct, [('a1', BLong, -1),
                                       ('a2', BChar, -1),
                                       ('a3', BShort, -1)])
    d = _getfields(BStruct)
    assert len(d) == 3
    assert d[0][0] == 'a1'
    assert d[0][1].type is BLong
    assert d[0][1].offset == 0
    assert d[0][1].bitsize == -1
    assert d[1][0] == 'a2'
    assert d[1][1].type is BChar
    assert d[1][1].offset == sizeof_type(BLong)
    assert d[1][1].bitsize == -1
    assert d[2][0] == 'a3'
    assert d[2][1].type is BShort
    assert d[2][1].offset == sizeof_type(BLong) + sizeof_type(BShort)
    assert d[2][1].bitsize == -1
    assert sizeof_type(BStruct) == 2 * sizeof_type(BLong)
    assert alignof(BStruct) == alignof(BLong)

def test_complete_union():
    BLong = new_primitive_type("long")
    BChar = new_primitive_type("char")
    BUnion = new_union_type("foo")
    assert _getfields(BUnion) is None
    complete_struct_or_union(BUnion, [('a1', BLong, -1),
                                      ('a2', BChar, -1)])
    d = _getfields(BUnion)
    assert len(d) == 2
    assert d[0][0] == 'a1'
    assert d[0][1].type is BLong
    assert d[0][1].offset == 0
    assert d[0][1].bitsize == -1
    assert d[1][0] == 'a2'
    assert d[1][1].type is BChar
    assert d[1][1].offset == 0
    assert d[1][1].bitsize == -1
    assert sizeof_type(BUnion) == sizeof_type(BLong)
    assert alignof(BUnion) == alignof(BLong)

def test_struct_instance():
    BInt = new_primitive_type("int")
    BStruct = new_struct_type("foo")
    BStructPtr = new_pointer_type(BStruct)
    complete_struct_or_union(BStruct, [('a1', BInt, -1),
                                       ('a2', BInt, -1)])
    p = new(BStructPtr, None)
    s = p[0]
    assert s.a1 == 0
    s.a2 = 123
    assert s.a1 == 0
    assert s.a2 == 123

def test_struct_pointer():
    BInt = new_primitive_type("int")
    BStruct = new_struct_type("foo")
    BStructPtr = new_pointer_type(BStruct)
    complete_struct_or_union(BStruct, [('a1', BInt, -1),
                                       ('a2', BInt, -1)])
    p = new(BStructPtr, None)
    assert p.a1 == 0      # read/write via the pointer (C equivalent: '->')
    p.a2 = 123
    assert p.a1 == 0
    assert p.a2 == 123

def test_struct_init_list():
    BInt = new_primitive_type("int")
    BStruct = new_struct_type("foo")
    BStructPtr = new_pointer_type(BStruct)
    complete_struct_or_union(BStruct, [('a1', BInt, -1),
                                       ('a2', BInt, -1),
                                       ('a3', BInt, -1)])
    s = new(BStructPtr, [123, 456])
    assert s.a1 == 123
    assert s.a2 == 456
    assert s.a3 == 0
