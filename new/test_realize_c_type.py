import os

def setup_module():
    os.system("python setup.py build_ext -i")
    global realize_c_type
    import realize_c_type


def test_void():
    assert realize_c_type.test("void") == "VOID"

def test_int_star():
    assert realize_c_type.test("int *") == ("pointer", "INT")
