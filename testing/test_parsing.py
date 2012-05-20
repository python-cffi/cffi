from ffi import FFI
from ffi.backend_base import BackendBase

class FakeBackend(BackendBase):
    
    def load_library(self, name=Ellipsis):
        assert name in [Ellipsis, "foobar"]
        return FakeLibrary()

    def new_primitive_type(self, name):
        return '<%s>' % name

    def new_pointer_type(self, itemtype):
        return '<pointer to %s>' % (itemtype,)

class FakeLibrary(object):
    
    def load_function(self, name, args, result, varargs):
        return FakeFunction(name, args, result, varargs)

class FakeFunction(object):

    def __init__(self, name, args, result, varargs):
        self.name = name
        self.args = args
        self.result = result
        self.varargs = varargs


def test_simple():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("double sin(double x);")
    m = ffi.load("foobar")
    func = m.sin    # should be a callable on real backends
    assert func.name == 'sin'
    assert func.args == ['<double>']
    assert func.result == '<double>'
    assert func.varargs is False

def test_pipe():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("int pipe(int pipefd[2]);")
    func = ffi.C.pipe
    assert func.name == 'pipe'
    assert func.args == ['<pointer to <int>>']
    assert func.result == '<int>'
    assert func.varargs is False

def test_vararg():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("short foo(int, ...);")
    func = ffi.C.foo
    assert func.name == 'foo'
    assert func.args == ['<int>']
    assert func.result == '<short>'
    assert func.varargs is True
