from ffi import FFI
from ffi.backend_base import BackendBase

class FakeBackend(BackendBase):
    
    def load_library(self, name=Ellipsis):
        assert name in [Ellipsis, "foobar"]
        return FakeLibrary()

    def new_function_type(self, args, result, has_varargs):
        return '<func (%s), %s, %s>' % (', '.join(args), result, has_varargs)

    def new_primitive_type(self, name):
        return '<%s>' % name

    def new_pointer_type(self, itemtype):
        return '<pointer to %s>' % (itemtype,)

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
    m = ffi.load("foobar")
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
