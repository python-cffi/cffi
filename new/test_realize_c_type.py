

def check(input, expected_output=None):
    import _cffi1_backend
    ffi = _cffi1_backend.FFI()
    ct = ffi.typeof(input)
    assert isinstance(ct, ffi.CType)
    assert ct.cname == (expected_output or input)

def test_void():
    check("void", "void")
    check("  void  ", "void")

def test_int_star():
    check("int")
    check("int *")
    check("int*", "int *")

def test_noop():
    check("int(*)", "int *")

def test_array():
    check("int[5]")
