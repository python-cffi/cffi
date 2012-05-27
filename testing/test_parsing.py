from ffi import FFI

class FakeBackend(object):

    def nonstandard_integer_types(self):
        return {}

    def load_library(self, name):
        assert "libc" in name or "libm" in name
        return FakeLibrary()

    def new_function_type(self, ffi, args, result, has_varargs):
        return '<func (%s), %s, %s>' % (', '.join(args), result, has_varargs)

    def new_primitive_type(self, ffi, name):
        assert name == name.lower()
        return '<%s>' % name

    def new_pointer_type(self, ffi, itemtype):
        return '<pointer to %s>' % (itemtype,)

    def new_struct_type(self, ffi, name, fnames, btypes, bitfields):
        return '<struct %s: %s>' % (
            name,
            ', '.join([y + x for x, y in zip(fnames, btypes)]))

class FakeLibrary(object):
    
    def load_function(self, BType, name):
        return FakeFunction(BType, name)

class FakeFunction(object):

    def __init__(self, BType, name):
        self.BType = BType
        self.name = name


def test_simple():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("double sin(double x);")
    m = ffi.load("m")
    func = m.sin    # should be a callable on real backends
    assert func.name == 'sin'
    assert func.BType == '<func (<double>), <double>, False>'

def test_pipe():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("int pipe(int pipefd[2]);")
    func = ffi.C.pipe
    assert func.name == 'pipe'
    assert func.BType == '<func (<pointer to <int>>), <int>, False>'

def test_vararg():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("short foo(int, ...);")
    func = ffi.C.foo
    assert func.name == 'foo'
    assert func.BType == '<func (<int>), <short>, True>'

def test_no_args():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("""
        int foo(void);
        """)
    assert ffi.C.foo.BType == '<func (), <int>, False>'

def test_typedef():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("""
        typedef unsigned int UInt;
        typedef UInt UIntReally;
        UInt foo(void);
        """)
    assert ffi.typeof("UIntReally") == '<unsigned int>'
    assert ffi.C.foo.BType == '<func (), <unsigned int>, False>'

def test_typedef_more_complex():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("""
        typedef struct { int a, b; } foo_t, *foo_p;
        int foo(foo_p[]);
        """)
    assert ffi.typeof("foo_t") == '<struct None: <int>a, <int>b>'
    assert ffi.typeof("foo_p") == '<pointer to <struct None: <int>a, <int>b>>'
    assert ffi.C.foo.BType == ('<func (<pointer to <pointer to <struct'
                               ' None: <int>a, <int>b>>>), <int>, False>')
