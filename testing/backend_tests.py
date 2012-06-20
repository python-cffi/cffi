import py
import sys, ctypes
from cffi import FFI

SIZE_OF_INT   = ctypes.sizeof(ctypes.c_int)
SIZE_OF_LONG  = ctypes.sizeof(ctypes.c_long)
SIZE_OF_SHORT = ctypes.sizeof(ctypes.c_short)
SIZE_OF_PTR   = ctypes.sizeof(ctypes.c_void_p)
#SIZE_OF_WCHAR = ctypes.sizeof(ctypes.c_wchar)


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
                self._test_int_type(ffi, c_decl, size, unsigned)

    def test_fixedsize_int(self):
        ffi = FFI(backend=self.Backend())
        for size in [1, 2, 4, 8]:
            self._test_int_type(ffi, 'int%d_t' % (8*size), size, False)
            self._test_int_type(ffi, 'uint%d_t' % (8*size), size, True)
        self._test_int_type(ffi, 'intptr_t', SIZE_OF_PTR, False)
        self._test_int_type(ffi, 'uintptr_t', SIZE_OF_PTR, True)
        self._test_int_type(ffi, 'ptrdiff_t', SIZE_OF_PTR, False)
        self._test_int_type(ffi, 'size_t', SIZE_OF_PTR, True)
        self._test_int_type(ffi, 'ssize_t', SIZE_OF_PTR, False)
        #self._test_int_type(ffi, 'wchar_t', SIZE_OF_WCHAR, True)

    def _test_int_type(self, ffi, c_decl, size, unsigned):
        if unsigned:
            min = 0
            max = (1 << (8*size)) - 1
        else:
            min = -(1 << (8*size-1))
            max = (1 << (8*size-1)) - 1
        min = int(min)
        max = int(max)
        p = ffi.cast(c_decl, min)
        assert p != min       # no __eq__(int)
        assert bool(p) is True
        assert int(p) == min
        p = ffi.cast(c_decl, max)
        assert int(p) == max
        p = ffi.cast(c_decl, long(max))
        assert int(p) == max
        q = ffi.cast(c_decl, min - 1)
        assert ffi.typeof(q) is ffi.typeof(p) and int(q) == max
        q = ffi.cast(c_decl, long(min - 1))
        assert ffi.typeof(q) is ffi.typeof(p) and int(q) == max
        assert q != p
        assert hash(q) != hash(p)   # unlikely
        py.test.raises(OverflowError, ffi.new, c_decl, min - 1)
        py.test.raises(OverflowError, ffi.new, c_decl, max + 1)
        py.test.raises(OverflowError, ffi.new, c_decl, long(min - 1))
        py.test.raises(OverflowError, ffi.new, c_decl, long(max + 1))
        assert ffi.new(c_decl, min)[0] == min
        assert ffi.new(c_decl, max)[0] == max
        assert ffi.new(c_decl, long(min))[0] == min
        assert ffi.new(c_decl, long(max))[0] == max

    def test_new_single_integer(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int")     # similar to ffi.new("int[1]")
        assert p[0] == 0
        p[0] = -123
        assert p[0] == -123
        p = ffi.new("int", -42)
        assert p[0] == -42
        assert repr(p) == "<cdata 'int *' owning %d bytes>" % SIZE_OF_INT

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
        p = ffi.new("int[4]", [ffi.cast("int", -5)])
        assert p[0] == -5
        assert repr(p) == "<cdata 'int[4]' owning %d bytes>" % (4*SIZE_OF_INT)

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
        assert repr(p) == "<cdata 'int[]' owning %d bytes>" % (2*SIZE_OF_INT)
        #
        p = ffi.new("int[]", 0)
        py.test.raises(IndexError, "p[0]")
        py.test.raises(ValueError, ffi.new, "int[]", -1)
        assert repr(p) == "<cdata 'int[]' owning 0 bytes>"

    def test_pointer_init(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("int", 24)
        a = ffi.new("int *[10]", [None, None, n, n, None])
        for i in range(10):
            if i not in (2, 3):
                assert a[i] is None
        assert a[2] == a[3] == n

    def test_cannot_cast(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[10]")
        e = py.test.raises(TypeError, ffi.new, "long int *", a)
        msg = str(e.value)
        assert "'short[10]'" in msg and "'long *'" in msg

    def test_new_pointer_to_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("int[4]", [100, 102, 104, 106])
        p = ffi.new("int *", a)
        assert p[0] == ffi.cast("int *", a)
        assert p[0][2] == 104
        p = ffi.cast("int *", a)
        assert p[0] == 100
        assert p[1] == 102
        assert p[2] == 104
        assert p[3] == 106
        # keepalive: a

    def test_pointer_direct(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.cast("int*", 0)
        assert p is not None
        assert bool(p) is False
        assert p == ffi.cast("int*", 0)
        assert p == ffi.cast("int*", None)
        assert p == None == p
        a = ffi.new("int[]", [123, 456])
        p = ffi.cast("int*", a)
        assert bool(p) is True
        assert p == ffi.cast("int*", a)
        assert p != ffi.cast("int*", 0)
        assert p[0] == 123
        assert p[1] == 456

    def test_repr(self):
        typerepr = self.TypeRepr
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { short a, b, c; };")
        p = ffi.cast("unsigned short int", 0)
        assert repr(p) == "<cdata 'unsigned short'>"
        assert repr(ffi.typeof(p)) == typerepr % "unsigned short"
        p = ffi.cast("int*", 0)
        assert repr(p) == "<cdata 'int *'>"
        assert repr(ffi.typeof(p)) == typerepr % "int *"
        #
        p = ffi.new("int")
        assert repr(p) == "<cdata 'int *' owning %d bytes>" % SIZE_OF_INT
        assert repr(ffi.typeof(p)) == typerepr % "int *"
        p = ffi.new("int*")
        assert repr(p) == "<cdata 'int * *' owning %d bytes>" % SIZE_OF_PTR
        assert repr(ffi.typeof(p)) == typerepr % "int * *"
        p = ffi.new("int [2]")
        assert repr(p) == "<cdata 'int[2]' owning %d bytes>" % (2*SIZE_OF_INT)
        assert repr(ffi.typeof(p)) == typerepr % "int[2]"
        p = ffi.new("int*[2][3]")
        assert repr(p) == "<cdata 'int *[2][3]' owning %d bytes>" % (
            6*SIZE_OF_PTR)
        assert repr(ffi.typeof(p)) == typerepr % "int *[2][3]"
        p = ffi.new("struct foo")
        assert repr(p) == "<cdata 'struct foo *' owning %d bytes>" % (
            3*SIZE_OF_SHORT)
        assert repr(ffi.typeof(p)) == typerepr % "struct foo *"
        #
        q = ffi.cast("short", -123)
        assert repr(q) == "<cdata 'short'>"
        assert repr(ffi.typeof(q)) == typerepr % "short"
        p = ffi.new("int")
        q = ffi.cast("short*", p)
        assert repr(q) == "<cdata 'short *'>"
        assert repr(ffi.typeof(q)) == typerepr % "short *"
        p = ffi.new("int [2]")
        q = ffi.cast("int*", p)
        assert repr(q) == "<cdata 'int *'>"
        assert repr(ffi.typeof(q)) == typerepr % "int *"
        p = ffi.new("struct foo")
        q = ffi.cast("struct foo *", p)
        assert repr(q) == "<cdata 'struct foo *'>"
        assert repr(ffi.typeof(q)) == typerepr % "struct foo *"
        q = q[0]
        assert repr(q) == "<cdata 'struct foo'>"
        assert repr(ffi.typeof(q)) == typerepr % "struct foo"

    def test_new_array_of_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[3][4]")
        p[0][0] = 10
        p[2][3] = 33
        assert p[0][0] == 10
        assert p[2][3] == 33
        py.test.raises(IndexError, "p[1][-1]")

    def test_constructor_array_of_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int[3][2]", [[10, 11], [12, 13], [14, 15]])
        assert p[2][1] == 15

    def test_new_array_of_pointer_1(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("int", 99)
        p = ffi.new("int*[4]")
        p[3] = n
        a = p[3]
        assert repr(a) == "<cdata 'int *'>"
        assert a[0] == 99

    def test_new_array_of_pointer_2(self):
        ffi = FFI(backend=self.Backend())
        n = ffi.new("int[1]", [99])
        p = ffi.new("int*[4]")
        p[3] = n
        a = p[3]
        assert repr(a) == "<cdata 'int *'>"
        assert a[0] == 99

    def test_char(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.new("char", "\xff")[0] == '\xff'
        assert ffi.new("char")[0] == '\x00'
        assert int(ffi.cast("char", 300)) == 300 - 256
        assert bool(ffi.new("char"))
        py.test.raises(TypeError, ffi.new, "char", 32)
        py.test.raises(TypeError, ffi.new, "char", "foo")
        #
        p = ffi.new("char[]", ['a', 'b', '\x9c'])
        assert len(p) == 3
        assert p[0] == 'a'
        assert p[1] == 'b'
        assert p[2] == '\x9c'
        p[0] = '\xff'
        assert p[0] == '\xff'
        p = ffi.new("char[]", "abcd")
        assert len(p) == 5
        assert p[4] == '\x00'    # like in C, with:  char[] p = "abcd";
        #
        p = ffi.new("char[4]", "ab")
        assert len(p) == 4
        assert [p[i] for i in range(4)] == ['a', 'b', '\x00', '\x00']
        p = ffi.new("char[2]", "ab")
        assert len(p) == 2
        assert [p[i] for i in range(2)] == ['a', 'b']
        py.test.raises(IndexError, ffi.new, "char[2]", "abc")

    def test_none_as_null(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int*[1]")
        assert p[0] is None
        #
        n = ffi.new("int", 99)
        p = ffi.new("int*[]", [n])
        assert p[0][0] == 99
        p[0] = None
        assert p[0] is None

    def test_float(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("float[]", [-2, -2.5])
        assert p[0] == -2.0
        assert p[1] == -2.5
        p[1] += 17.75
        assert p[1] == 15.25
        #
        p = ffi.new("float", 15.75)
        assert p[0] == 15.75
        py.test.raises(TypeError, int, p)
        py.test.raises(TypeError, float, p)
        p[0] = 0.0
        assert bool(p) is True
        #
        p = ffi.new("float", 1.1)
        f = p[0]
        assert f != 1.1      # because of rounding effect
        assert abs(f - 1.1) < 1E-7
        #
        INF = 1E200 * 1E200
        assert 1E200 != INF
        p[0] = 1E200
        assert p[0] == INF     # infinite, not enough precision

    def test_struct_simple(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo")
        assert s.a == s.b == s.c == 0
        s.b = -23
        assert s.b == -23
        py.test.raises(OverflowError, "s.b = 32768")
        #
        s = ffi.new("struct foo", [-2, -3])
        assert s.a == -2
        assert s.b == -3
        assert s.c == 0
        py.test.raises((AttributeError, TypeError), "del s.a")
        assert repr(s) == "<cdata 'struct foo *' owning %d bytes>" % (
            SIZE_OF_INT + 2 * SIZE_OF_SHORT)
        #
        py.test.raises(ValueError, ffi.new, "struct foo", [1, 2, 3, 4])

    def test_constructor_struct_from_dict(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo", {'b': 123, 'c': 456})
        assert s.a == 0
        assert s.b == 123
        assert s.c == 456
        py.test.raises(KeyError, ffi.new, "struct foo", {'d': 456})

    def test_struct_pointer(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo")
        assert s[0].a == s[0].b == s[0].c == 0
        s[0].b = -23
        assert s[0].b == s.b == -23
        py.test.raises(OverflowError, "s[0].b = -32769")
        py.test.raises(IndexError, "s[1]")

    def test_struct_opaque(self):
        ffi = FFI(backend=self.Backend())
        py.test.raises(TypeError, ffi.new, "struct baz")
        p = ffi.new("struct baz *")    # this works
        assert p[0] is None

    def test_pointer_to_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a; short b, c; };")
        s = ffi.new("struct foo")
        s.a = -42
        assert s[0].a == -42
        p = ffi.new("struct foo *", s)
        assert p[0].a == -42
        assert p[0][0].a == -42
        p[0].a = -43
        assert s.a == -43
        assert s[0].a == -43
        p[0][0].a = -44
        assert s.a == -44
        assert s[0].a == -44
        s.a = -45
        assert p[0].a == -45
        assert p[0][0].a == -45
        s[0].a = -46
        assert p[0].a == -46
        assert p[0][0].a == -46

    def test_constructor_struct_of_array(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a[2]; char b[3]; };")
        s = ffi.new("struct foo", [[10, 11], ['a', 'b', 'c']])
        assert s.a[1] == 11
        assert s.b[2] == 'c'
        s.b[1] = 'X'
        assert s.b[0] == 'a'
        assert s.b[1] == 'X'
        assert s.b[2] == 'c'

    def test_recursive_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int value; struct foo *next; };")
        s = ffi.new("struct foo")
        t = ffi.new("struct foo")
        s.value = 123
        s.next = t
        t.value = 456
        assert s.value == 123
        assert s.next.value == 456

    def test_union_simple(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("union foo { int a; short b, c; };")
        u = ffi.new("union foo")
        assert u.a == u.b == u.c == 0
        u.b = -23
        assert u.b == -23
        assert u.a != 0
        py.test.raises(OverflowError, "u.b = 32768")
        #
        u = ffi.new("union foo", -2)
        assert u.a == -2
        py.test.raises((AttributeError, TypeError), "del u.a")
        assert repr(u) == "<cdata 'union foo *' owning %d bytes>" % SIZE_OF_INT

    def test_union_opaque(self):
        ffi = FFI(backend=self.Backend())
        py.test.raises(TypeError, ffi.new, "union baz")
        u = ffi.new("union baz *")   # this works
        assert u[0] is None

    def test_sizeof_type(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("""
            struct foo { int a; short b, c, d; };
            union foo { int a; short b, c, d; };
        """)
        for c_type, expected_size in [
            ('char', 1),
            ('unsigned int', 4),
            ('char *', SIZE_OF_LONG),
            ('int[5]', 20),
            ('struct foo', 12),
            ('union foo', 4),
            ]:
            size = ffi.sizeof(c_type)
            assert size == expected_size

    def test_sizeof_cdata(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.sizeof(ffi.new("short")) == SIZE_OF_PTR
        assert ffi.sizeof(ffi.cast("short", 123)) == SIZE_OF_SHORT
        #
        a = ffi.new("int[]", [10, 11, 12, 13, 14])
        assert len(a) == 5
        assert ffi.sizeof(a) == 5 * SIZE_OF_INT

    def test_str_from_char_pointer(self):
        ffi = FFI(backend=self.Backend())
        assert str(ffi.new("char", "x")) == "x"
        assert str(ffi.new("char", "\x00")) == ""

    def test_string_from_char_array(self):
        ffi = FFI(backend=self.Backend())
        assert str(ffi.cast("char", "x")) == "x"
        p = ffi.new("char[]", "hello.")
        p[5] = '!'
        assert str(p) == "hello!"
        p[6] = '?'
        assert str(p) == "hello!?"
        p[3] = '\x00'
        assert str(p) == "hel"
        py.test.raises(IndexError, "p[7] = 'X'")
        #
        a = ffi.new("char[]", "hello\x00world")
        assert len(a) == 12
        p = ffi.cast("char *", a)
        assert str(p) == 'hello'

    def test_fetch_const_char_p_field(self):
        # 'const' is ignored so far
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { const char *name; };")
        t = ffi.new("const char[]", "testing")
        s = ffi.new("struct foo", [t])
        assert type(s.name) is not str
        assert str(s.name) == "testing"
        s.name = None
        assert s.name is None

    def test_voidp(self):
        ffi = FFI(backend=self.Backend())
        py.test.raises(TypeError, ffi.new, "void")
        p = ffi.new("void *")
        assert p[0] is None
        a = ffi.new("int[]", [10, 11, 12])
        p = ffi.new("void *", a)
        vp = p[0]
        py.test.raises(TypeError, "vp[0]")
        py.test.raises(TypeError, ffi.new, "short *", a)
        #
        ffi.cdef("struct foo { void *p; int *q; short *r; };")
        s = ffi.new("struct foo")
        s.p = a    # works
        s.q = a    # works
        py.test.raises(TypeError, "s.r = a")    # fails
        b = ffi.cast("int *", a)
        s.p = b    # works
        s.q = b    # works
        py.test.raises(TypeError, "s.r = b")    # fails

    def test_functionptr_simple(self):
        ffi = FFI(backend=self.Backend())
        py.test.raises(TypeError, ffi.callback, "int(*)(int)")
        py.test.raises(TypeError, ffi.callback, "int(*)(int)", 0)
        def cb(n):
            return n + 1
        p = ffi.callback("int(*)(int)", cb)
        res = p(41)     # calling an 'int(*)(int)', i.e. a function pointer
        assert res == 42 and type(res) is int
        res = p(ffi.cast("int", -41))
        assert res == -40 and type(res) is int
        assert repr(p).startswith(
            "<cdata 'int(*)(int)' calling <function cb at 0x")
        assert ffi.typeof(p) is ffi.typeof("int(*)(int)")
        q = ffi.new("int(*)(int)", p)
        assert repr(q) == "<cdata 'int(* *)(int)' owning %d bytes>" % (
            SIZE_OF_PTR)
        py.test.raises(TypeError, "q(43)")
        res = q[0](43)
        assert res == 44
        q = ffi.cast("int(*)(int)", p)
        assert repr(q) == "<cdata 'int(*)(int)'>"
        res = q(45)
        assert res == 46

    def test_functionptr_advanced(self):
        ffi = FFI(backend=self.Backend())
        t = ffi.typeof("int(*(*)(int))(int)")
        assert repr(t) == self.TypeRepr % "int(*(*)(int))(int)"

    def test_functionptr_voidptr_return(self):
        ffi = FFI(backend=self.Backend())
        def cb():
            return None
        p = ffi.callback("void*(*)()", cb)
        res = p()
        assert res is None
        int_ptr = ffi.new('int')
        void_ptr = ffi.cast('void*', int_ptr)
        def cb():
            return void_ptr
        p = ffi.callback("void*(*)()", cb)
        res = p()
        assert repr(res) == "<cdata 'void *'>"
        assert ffi.cast("long", res) != 0

    def test_functionptr_intptr_return(self):
        ffi = FFI(backend=self.Backend())
        def cb():
            return None
        p = ffi.callback("int*(*)()", cb)
        res = p()
        assert res is None
        int_ptr = ffi.new('int')
        def cb():
            return int_ptr
        p = ffi.callback("int*(*)()", cb)
        res = p()
        assert repr(res) == "<cdata 'int *'>"
        assert ffi.cast("long", res) != 0
        int_array_ptr = ffi.new('int[1]')
        def cb():
            return int_array_ptr
        p = ffi.callback("int*(*)()", cb)
        res = p()
        assert repr(res) == "<cdata 'int *'>"
        assert ffi.cast("long", res) != 0

    def test_functionptr_void_return(self):
        ffi = FFI(backend=self.Backend())
        def foo():
            pass
        foo_cb = ffi.callback("void foo()", foo)
        result = foo_cb()
        assert result is None

    def test_char_cast(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.cast("int", '\x01')
        assert ffi.typeof(p) is ffi.typeof("int")
        assert int(p) == 1
        p = ffi.cast("int", ffi.cast("char", "a"))
        assert int(p) == ord("a")
        p = ffi.cast("int", ffi.cast("char", "\x80"))
        assert int(p) == 0x80     # "char" is considered unsigned in this case
        p = ffi.cast("int", "\x81")
        assert int(p) == 0x81

    def test_cast_array_to_charp(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[]", [0x1234, 0x5678])
        p = ffi.cast("char*", a)
        data = ''.join([p[i] for i in range(4)])
        if sys.byteorder == 'little':
            assert data == '\x34\x12\x78\x56'
        else:
            assert data == '\x12\x34\x56\x78'

    def test_cast_between_pointers(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[]", [0x1234, 0x5678])
        p = ffi.cast("short*", a)
        p2 = ffi.cast("int*", p)
        q = ffi.cast("char*", p2)
        data = ''.join([q[i] for i in range(4)])
        if sys.byteorder == 'little':
            assert data == '\x34\x12\x78\x56'
        else:
            assert data == '\x12\x34\x56\x78'

    def test_cast_pointer_and_int(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short int[]", [0x1234, 0x5678])
        l1 = ffi.cast("intptr_t", a)
        p = ffi.cast("short*", a)
        l2 = ffi.cast("intptr_t", p)
        assert int(l1) == int(l2) != 0
        q = ffi.cast("short*", l1)
        assert q == ffi.cast("short*", int(l1))
        assert q[0] == 0x1234
        assert int(ffi.cast("intptr_t", None)) == 0

    def test_cast_functionptr_and_int(self):
        ffi = FFI(backend=self.Backend())
        def cb(n):
            return n + 1
        a = ffi.callback("int(*)(int)", cb)
        p = ffi.cast("void *", a)
        assert p
        b = ffi.cast("int(*)(int)", p)
        assert b(41) == 42
        assert a == b
        assert hash(a) == hash(b)

    def test_cast_float(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.cast("float", 12)
        assert float(a) == 12.0
        a = ffi.cast("float", 12.5)
        assert float(a) == 12.5
        a = ffi.cast("float", "A")
        assert float(a) == ord("A")
        a = ffi.cast("int", 12.9)
        assert int(a) == 12
        a = ffi.cast("char", 66.9 + 256)
        assert str(a) == "B"
        #
        a = ffi.cast("float", ffi.cast("int", 12))
        assert float(a) == 12.0
        a = ffi.cast("float", ffi.cast("double", 12.5))
        assert float(a) == 12.5
        a = ffi.cast("float", ffi.cast("char", "A"))
        assert float(a) == ord("A")
        a = ffi.cast("int", ffi.cast("double", 12.9))
        assert int(a) == 12
        a = ffi.cast("char", ffi.cast("double", 66.9 + 256))
        assert str(a) == "B"

    def test_enum(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo { A, B, CC, D };")
        assert int(ffi.cast("enum foo", "A")) == 0
        assert int(ffi.cast("enum foo", "B")) == 1
        assert int(ffi.cast("enum foo", "CC")) == 2
        assert int(ffi.cast("enum foo", "D")) == 3
        ffi.cdef("enum bar { A, B=-2, CC, D };")
        assert int(ffi.cast("enum bar", "A")) == 0
        assert int(ffi.cast("enum bar", "B")) == -2
        assert int(ffi.cast("enum bar", "CC")) == -1
        assert int(ffi.cast("enum bar", "D")) == 0
        assert ffi.cast("enum bar", "B") != ffi.cast("enum bar", "B")
        assert ffi.cast("enum foo", "A") != ffi.cast("enum bar", "A")
        assert ffi.cast("enum bar", "A") != ffi.cast("int", 0)
        assert repr(ffi.cast("enum bar", "CC")) == "<cdata 'enum bar'>"

    def test_enum_in_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo { A, B, C, D }; struct bar { enum foo e; };")
        s = ffi.new("struct bar")
        s.e = 0
        assert s.e == "A"
        s.e = "D"
        assert s.e == "D"
        assert s[0].e == "D"
        s[0].e = "C"
        assert s.e == "C"
        assert s[0].e == "C"
        s.e = ffi.cast("enum foo", -1)
        assert s.e == '#-1'
        assert s[0].e == '#-1'
        s.e = s.e
        py.test.raises(TypeError, "s.e = None")

    def test_enum_non_contiguous(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("enum foo { A, B=42, C };")
        assert int(ffi.cast("enum foo", "A")) == 0
        assert int(ffi.cast("enum foo", "B")) == 42
        assert int(ffi.cast("enum foo", "C")) == 43
        assert str(ffi.cast("enum foo", 0)) == "A"
        assert str(ffi.cast("enum foo", 42)) == "B"
        assert str(ffi.cast("enum foo", 43)) == "C"
        invalid_value = ffi.cast("enum foo", 2)
        assert int(invalid_value) == 2
        assert str(invalid_value) == "#2"

    def test_array_of_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a, b; };")
        s = ffi.new("struct foo[1]")
        py.test.raises(AttributeError, 's.b')
        py.test.raises(AttributeError, 's.b = 412')
        s[0].b = 412
        assert s[0].b == 412
        py.test.raises(IndexError, 's[1]')

    def test_pointer_to_array(self):
        ffi = FFI(backend=self.Backend())
        p = ffi.new("int(*)[5]")
        assert repr(p) == "<cdata 'int(* *)[5]' owning %d bytes>" % SIZE_OF_PTR

    def test_iterate_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("char[]", "hello")
        assert list(a) == ["h", "e", "l", "l", "o", chr(0)]
        assert list(iter(a)) == ["h", "e", "l", "l", "o", chr(0)]
        #
        py.test.raises(TypeError, iter, ffi.cast("char *", a))
        py.test.raises(TypeError, list, ffi.cast("char *", a))
        py.test.raises(TypeError, iter, ffi.new("int"))
        py.test.raises(TypeError, list, ffi.new("int"))

    def test_offsetof(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a, b, c; };")
        assert ffi.offsetof("struct foo", "a") == 0
        assert ffi.offsetof("struct foo", "b") == 4
        assert ffi.offsetof("struct foo", "c") == 8

    def test_alignof(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { char a; short b; char c; };")
        assert ffi.alignof("int") == 4
        assert ffi.alignof("double") in (4, 8)
        assert ffi.alignof("struct foo") == 2

    def test_bitfield(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo { int a:10, b:20, c:3; };")
        assert ffi.sizeof("struct foo") == 8
        s = ffi.new("struct foo")
        s.a = 511
        py.test.raises(OverflowError, "s.a = 512")
        py.test.raises(OverflowError, "s[0].a = 512")
        assert s.a == 511
        s.a = -512
        py.test.raises(OverflowError, "s.a = -513")
        py.test.raises(OverflowError, "s[0].a = -513")
        assert s.a == -512
        s.c = 3
        assert s.c == 3
        py.test.raises(OverflowError, "s.c = 4")
        py.test.raises(OverflowError, "s[0].c = 4")
        s.c = -4
        assert s.c == -4

    def test_anonymous_struct(self):
        ffi = FFI(backend=self.Backend())
        ffi.cdef("typedef struct { int a; } foo_t;")
        ffi.cdef("typedef struct { char b, c; } bar_t;")
        f = ffi.new("foo_t", [12345])
        b = ffi.new("bar_t", ["B", "C"])
        assert f.a == 12345
        assert b.b == "B"
        assert b.c == "C"
        assert repr(b).startswith("<cdata 'struct $bar_t *'")

    def test_struct_with_two_usages(self):
        for name in ['foo_s', '']:    # anonymous or not
            ffi = FFI(backend=self.Backend())
            ffi.cdef("typedef struct %s { int a; } foo_t, *foo_p;" % name)
            f = ffi.new("foo_t", [12345])
            ps = ffi.new("foo_p[]", [f])

    def test_pointer_arithmetic(self):
        ffi = FFI(backend=self.Backend())
        s = ffi.new("short[]", range(100, 110))
        p = ffi.cast("short *", s)
        assert p[2] == 102
        assert p+1 == p+1
        assert p+1 != p+0
        assert p == p+0 == p-0
        assert (p+1)[0] == 101
        assert (p+19)[-10] == 109
        assert (p+5) - (p+1) == 4
        assert p == s+0
        assert p+1 == s+1

    def test_ffi_buffer_ptr(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short", 100)
        b = ffi.buffer(a)
        assert type(b) is buffer
        assert len(str(b)) == 2
        if sys.byteorder == 'little':
            assert str(b) == '\x64\x00'
            b[0] = '\x65'
        else:
            assert str(b) == '\x00\x64'
            b[1] = '\x65'
        assert a[0] == 101

    def test_ffi_buffer_array(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("int[]", range(100, 110))
        b = ffi.buffer(a)
        assert type(b) is buffer
        if sys.byteorder == 'little':
            assert str(b).startswith('\x64\x00\x00\x00\x65\x00\x00\x00')
            b[4] = '\x45'
        else:
            assert str(b).startswith('\x00\x00\x00\x64\x00\x00\x00\x65')
            b[7] = '\x45'
        assert len(str(b)) == 4 * 10
        assert a[1] == 0x45

    def test_ffi_buffer_ptr_size(self):
        ffi = FFI(backend=self.Backend())
        a = ffi.new("short", 0x4243)
        b = ffi.buffer(a, 1)
        assert type(b) is buffer
        assert len(str(b)) == 1
        if sys.byteorder == 'little':
            assert str(b) == '\x43'
            b[0] = '\x62'
            assert a[0] == 0x4262
        else:
            assert str(b) == '\x42'
            b[0] = '\x63'
            assert a[0] == 0x6343

    def test_ffi_buffer_array_size(self):
        ffi = FFI(backend=self.Backend())
        a1 = ffi.new("int[]", range(100, 110))
        a2 = ffi.new("int[]", range(100, 115))
        assert str(ffi.buffer(a1)) == str(ffi.buffer(a2, 4*10))

    def test_ffi_buffer_with_file(self):
        ffi = FFI(backend=self.Backend())
        import tempfile, os, array
        fd, filename = tempfile.mkstemp()
        f = os.fdopen(fd, 'r+b')
        a = ffi.new("int[]", range(1005))
        f.write(ffi.buffer(a, 1000 * ffi.sizeof("int")))
        f.seek(0)
        assert f.read() == array.array('i', range(1000)).tostring()
        f.seek(0)
        b = ffi.new("int[]", 1005)
        f.readinto(ffi.buffer(b, 1000 * ffi.sizeof("int")))
        assert list(a)[:1000] + [0] * (len(a)-1000) == list(b)
        f.close()
        os.unlink(filename)

    def test_new_struct_containing_array_varsize(self):
        py.test.skip("later?")
        ffi = FFI(backend=self.Backend())
        ffi.cdef("struct foo_s { int len; short data[]; };")
        p = ffi.new("struct foo_s", 10)     # a single integer is the length
        assert p.len == 0
        assert p.data[9] == 0
        py.test.raises(IndexError, "p.data[10]")

    def test_ffi_typeof_getcname(self):
        ffi = FFI(backend=self.Backend())
        assert ffi.getctype("int") == "int"
        assert ffi.getctype("int", 'x') == "int x"
        assert ffi.getctype("int*") == "int *"
        assert ffi.getctype("int*", '') == "int *"
        assert ffi.getctype("int", '*') == "int *"
        assert ffi.getctype("int", ' * x ') == "int * x"
        assert ffi.getctype(ffi.typeof("int*"), '*') == "int * *"
        assert ffi.getctype("int", '[5]') == "int[5]"
        assert ffi.getctype("int[5]", '[6]') == "int[6][5]"
        assert ffi.getctype("int[5]", '(*)') == "int(*)[5]"
        # special-case for convenience: automatically put '()' around '*'
        assert ffi.getctype("int[5]", '*') == "int(*)[5]"
        assert ffi.getctype("int[5]", '*foo') == "int(*foo)[5]"
        assert ffi.getctype("int[5]", ' ** foo ') == "int(** foo)[5]"
