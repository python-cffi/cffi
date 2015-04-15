from recompiler import Recompiler, make_c_source
from cffi1 import FFI
from udir import udir


def check_type_table(input, expected_output):
    ffi = FFI()
    ffi.cdef(input)
    recompiler = Recompiler(ffi)
    recompiler.collect_type_table()
    assert ''.join(map(str, recompiler.cffi_types)) == expected_output

def test_type_table_func():
    check_type_table("double sin(double);",
                     "(FUNCTION 1)(PRIMITIVE 14)(FUNCTION_END 0)")
    check_type_table("float sin(double);",
                     "(FUNCTION 3)(PRIMITIVE 14)(FUNCTION_END 0)(PRIMITIVE 13)")
    check_type_table("float sin(void);",
                     "(FUNCTION 2)(FUNCTION_END 0)(PRIMITIVE 13)")
    check_type_table("double sin(float); double cos(float);",
                     "(FUNCTION 3)(PRIMITIVE 13)(FUNCTION_END 0)(PRIMITIVE 14)")
    check_type_table("double sin(float); double cos(double);",
                     "(FUNCTION 1)(PRIMITIVE 14)(FUNCTION_END 0)"   # cos
                     "(FUNCTION 1)(PRIMITIVE 13)(FUNCTION_END 0)")  # sin
    check_type_table("float sin(double); float cos(float);",
                     "(FUNCTION 4)(PRIMITIVE 14)(FUNCTION_END 0)"   # sin
                     "(FUNCTION 4)(PRIMITIVE 13)(FUNCTION_END 0)")  # cos

def test_use_noop_for_repeated_args():
    check_type_table("double sin(double *, double *);",
                     "(FUNCTION 4)(POINTER 4)(NOOP 1)(FUNCTION_END 0)"
                     "(PRIMITIVE 14)")

def test_dont_use_noop_for_primitives():
    check_type_table("double sin(double, double);",
                     "(FUNCTION 1)(PRIMITIVE 14)(PRIMITIVE 14)(FUNCTION_END 0)")


def test_math_sin():
    ffi = FFI()
    ffi.cdef("double sin(double);")
    make_c_source(ffi, str(udir.join('math_sin.c')), '#include <math.h>')
