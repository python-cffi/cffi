from ffi import FFI


class FakeBackend(object):
    
    def load_library(self, name=Ellipsis):
        assert name in [Ellipsis, "foobar"]
        return FakeLibrary()

    def new_primitive_type(self, name):
        return '<%s>' % name

    def new_array_type(self, itemtype, length):
        return '<array[%d] of %s>' % (length, itemtype)

class FakeLibrary(object):
    
    def load_function(self, name, args, result):
        return FakeFunction(name, args, result)

class FakeFunction(object):

    def __init__(self, name, args, result):
        self.name = name
        self.args = args
        self.result = result


def test_simple():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("double sin(double x);")
    m = ffi.load("foobar")
    func = m.sin    # should be a callable on real backends
    assert func.name == 'sin'
    assert func.args == ['<double>']
    assert func.result == '<double>'

def test_pipe():
    ffi = FFI(backend=FakeBackend())
    ffi.cdef("int pipe(int pipefd[2]);")
    func = ffi.C.pipe
    assert func.name == 'pipe'
    assert func.args == ['<array[2] of <int>>']
    assert func.result == '<int>'
