import py
import sys
from ffi import FFI

SIZE_OF_LONG = 4 if sys.maxint == 2147483647 else 8


class BackendTests:

    def test_integer_ranges(self):
        ffi = FFI(backend=self.Backend())
        for (c_type, size) in [('char', 1),
                               ('short', 2),
                               ('short int', 2),
                               ('', 4),
                               ('int', 4),
                               ('long', SIZE_OF_LONG),
                               ('long int', SIZE_OF_LONG),
                               ('long long', 8),
                               ('long long int', 8),
                               ]:
            for unsigned in [None, False, True]:
                c_decl = {None: '',
                          False: 'signed ',
                          True: 'unsigned '}[unsigned] + c_type
                if c_decl == 'char' or c_decl == '':
                    continue
                if unsigned:
                    min = 0
                    max = (1 << (8*size)) - 1
                else:
                    min = -(1 << (8*size-1))
                    max = (1 << (8*size-1)) - 1
                p = ffi.new(c_decl, min)
                assert int(p) == min
                p = ffi.new(c_decl, max)
                assert int(p) == max
                py.test.raises(OverflowError, ffi.new, c_decl, min - 1)
                py.test.raises(OverflowError, ffi.new, c_decl, max + 1)

    def test_int_equality(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("short", -123)
        assert bool(n)
        assert n == -123
        assert n == ffi.new("int", -123)
        assert not bool(ffi.new("short", 0))
        assert n != ffi.new("short", 123)
        assert hash(n) == hash(-123)
        assert n < -122
        assert n <= -123
        assert n > -124
        assert n >= -123
        assert not (n < -123)
        assert not (n <= -124)
        assert not (n > -123)
        assert not (n >= -122)

    def test_new_array_no_arg(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[10]")
        # the object was zero-initialized:
        for i in range(10):
            assert p[i] == 0

    def test_array_indexing(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[10]")
        p[0] = 42
        p[9] = 43
        assert p[0] == 42
        assert p[9] == 43
        py.test.raises(IndexError, "p[10]")
        py.test.raises(IndexError, "p[10] = 44")
        py.test.raises(IndexError, "p[-1]")
        py.test.raises(IndexError, "p[-1] = 44")

    def test_new_array_args(self):
        ffi = FFI(backend=self.Backend())
        # this tries to be closer to C: where we say "int x[5] = {10, 20, ..}"
        # then here we must enclose the items in a list
        p = ffi.new("int[5]", [10, 20, 30, 40, 50])
        assert p[0] == 10
        assert p[1] == 20
        assert p[2] == 30
        assert p[3] == 40
        assert p[4] == 50
        p = ffi.new("int[4]", [25])
        assert p[0] == 25
        assert p[1] == 0     # follow C convention rather than LuaJIT's
        assert p[2] == 0
        assert p[3] == 0
        p = ffi.new("int[4]", [ffi.new("int", -5)])
        assert p[0] == -5

    def test_new_array_varsize(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[]", 10)     # a single integer is the length
        assert p[9] == 0
        py.test.raises(IndexError, "p[10]")
        #
        py.test.raises(TypeError, ffi.new, "int[]")
        #
        p = ffi.new("int[]", [-6, -7])    # a list is all the items, like C
        assert p[0] == -6
        assert p[1] == -7
        py.test.raises(IndexError, "p[2]")

    def test_cannot_cast(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[10]")
        e = py.test.raises(TypeError, ffi.new, "long int *", a)
        assert str(e.value) == "cannot convert 'short[10]' to 'long *'"

    def test_new_pointer_to_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("int[4]", [100, 102, 104, 106])
        p = ffi.new("int *", a)
        assert p[0] == 100
        assert p[1] == 102
        assert p[2] == 104
        assert p[3] == 106
        # keepalive: a

    def test_pointer_direct(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int*")
        assert bool(p) is False
        assert p == ffi.new("int*")
        a = ffi.new("int[]", [123, 456])
        p = ffi.new("int*", a)
        assert bool(p) is True
        assert p == ffi.new("int*", a)
        assert p != ffi.new("int*")
        assert p[0] == 123
        assert p[1] == 456

    def test_repr(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("unsigned short int")
        assert repr(p) == "<cdata 'unsigned short'>"
        assert repr(type(p)) == "<class 'ffi.CData<unsigned short>'>"
        p = ffi.new("int*")
        assert repr(p) == "<cdata 'int *'>"
        assert repr(type(p)) == "<class 'ffi.CData<int *>'>"
        p = ffi.new("int [2]")
        assert repr(p) == "<cdata 'int[2]'>"
        assert repr(type(p)) == "<class 'ffi.CData<int[2]>'>"
        p = ffi.new("int*[2][3]")
        assert repr(p) == "<cdata 'int *[2][3]'>"
        assert repr(type(p)) == "<class 'ffi.CData<int *[2][3]>'>"

    def test_new_array_of_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[3][4]")
        p[0][0] = 10
        p[2][3] = 33
        assert p[0][0] == 10
        assert p[2][3] == 33
        py.test.raises(IndexError, "p[1][-1]")
