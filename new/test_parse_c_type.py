import re
import os
import cffi

r_macro = re.compile(r"#define \w+[(][^\n]*")
r_define = re.compile(r"(#define \w+) [^\n]*")
header = open('parse_c_type.h').read()
header = r_macro.sub(r"", header)
header = r_define.sub(r"\1 ...", header)

ffi = cffi.FFI()
ffi.cdef(header)

lib = ffi.verify(open('parse_c_type.c').read(),
                 include_dirs=[os.getcwd()])

class ParseError(Exception):
    pass

def parse(input):
    out = ffi.new("_cffi_opcode_t[]", 100)
    info = ffi.new("struct _cffi_parse_info_s *")
    info.output = out
    info.output_size = len(out)
    for j in range(len(out)):
        out[j] = ffi.cast("void *", -424242)
    c_input = ffi.new("char[]", input)
    res = lib.parse_c_type(info, c_input)
    if res < 0:
        raise ParseError(ffi.string(info.error_message),
                         ffi.string(info.error_location) - c_input)
    assert 0 <= res < len(out)
    result = []
    for j in range(len(out)):
        if out[j] == ffi.cast("void *", -424242):
            assert res < j
            break
        i = int(ffi.cast("intptr_t", out[j]))
        if j == res:
            result.append('->')
        result.append(i)
    return result

def parsex(input):
    result = parse(input)
    def str_if_int(x):
        if isinstance(x, str):
            return x
        return '%d,%d' % (x & 255, x >> 8)
    return '  '.join(map(str_if_int, result))

def make_getter(name):
    opcode = getattr(lib, '_CFFI_OP_' + name)
    def getter(value):
        return opcode | (value << 8)
    return getter

Prim = make_getter('PRIMITIVE')
Pointer = make_getter('POINTER')
Array = make_getter('ARRAY')
OpenArray = make_getter('OPEN_ARRAY')
NoOp = make_getter('NOOP')
Func = make_getter('FUNCTION')
FuncEnd = make_getter('FUNCTION_END')


def test_simple():
    for simple_type, expected in [
            ("int", lib._CFFI_PRIM_INT),
            ("signed int", lib._CFFI_PRIM_INT),
            ("  long  ", lib._CFFI_PRIM_LONG),
            ("long int", lib._CFFI_PRIM_LONG),
            ("unsigned short", lib._CFFI_PRIM_USHORT),
            ("long double", lib._CFFI_PRIM_LONGDOUBLE),
            ]:
        assert parse(simple_type) == ['->', Prim(expected)]

def test_array():
    assert parse("int[5]") == [Prim(lib._CFFI_PRIM_INT), '->', Array(0), 5]
    assert parse("int[]") == [Prim(lib._CFFI_PRIM_INT), '->', OpenArray(0)]
    assert parse("int[5][8]") == [Prim(lib._CFFI_PRIM_INT),
                                  '->', Array(3),
                                  5,
                                  Array(0),
                                  8]
    assert parse("int[][8]") == [Prim(lib._CFFI_PRIM_INT),
                                 '->', OpenArray(2),
                                 Array(0),
                                 8]

def test_pointer():
    assert parse("int*") == [Prim(lib._CFFI_PRIM_INT), '->', Pointer(0)]
    assert parse("int***") == [Prim(lib._CFFI_PRIM_INT),
                               Pointer(0), Pointer(1), '->', Pointer(2)]

def test_grouping():
    assert parse("int*[]") == [Prim(lib._CFFI_PRIM_INT),
                               Pointer(0), '->', OpenArray(1)]
    assert parse("int**[][8]") == [Prim(lib._CFFI_PRIM_INT),
                                   Pointer(0), Pointer(1),
                                   '->', OpenArray(4), Array(2), 8]
    assert parse("int(*)[]") == [Prim(lib._CFFI_PRIM_INT),
                                 NoOp(3), '->', Pointer(1), OpenArray(0)]
    assert parse("int(*)[][8]") == [Prim(lib._CFFI_PRIM_INT),
                                    NoOp(3), '->', Pointer(1),
                                    OpenArray(4), Array(0), 8]
    assert parse("int**(**)") == [Prim(lib._CFFI_PRIM_INT),
                                  Pointer(0), Pointer(1),
                                  NoOp(2), Pointer(3), '->', Pointer(4)]
    assert parse("int**(**)[]") == [Prim(lib._CFFI_PRIM_INT),
                                    Pointer(0), Pointer(1),
                                    NoOp(6), Pointer(3), '->', Pointer(4),
                                    OpenArray(2)]

def test_simple_function():
    assert parse("int()") == [Prim(lib._CFFI_PRIM_INT),
                              '->', Func(0), FuncEnd(0), 0]
    assert parse("int(int)") == [Prim(lib._CFFI_PRIM_INT),
                                 '->', Func(0), NoOp(4), FuncEnd(0),
                                 Prim(lib._CFFI_PRIM_INT)]
    assert parse("int(long, char)") == [
                                 Prim(lib._CFFI_PRIM_INT),
                                 '->', Func(0), NoOp(5), NoOp(6), FuncEnd(0),
                                 Prim(lib._CFFI_PRIM_LONG),
                                 Prim(lib._CFFI_PRIM_CHAR)]
    assert parse("int(int*)") == [Prim(lib._CFFI_PRIM_INT),
                                  '->', Func(0), NoOp(5), FuncEnd(0),
                                  Prim(lib._CFFI_PRIM_INT),
                                  Pointer(4)]
    assert parse("int*(void)") == [Prim(lib._CFFI_PRIM_INT),
                                   Pointer(0),
                                   '->', Func(1), FuncEnd(0), 0]
    assert parse("int(int, ...)") == [Prim(lib._CFFI_PRIM_INT),
                                      '->', Func(0), NoOp(5), FuncEnd(1), 0,
                                      Prim(lib._CFFI_PRIM_INT)]

def test_internal_function():
    assert parse("int(*)()") == [Prim(lib._CFFI_PRIM_INT),
                                 NoOp(3), '->', Pointer(1),
                                 Func(0), FuncEnd(0), 0]
    assert parse("int(*())[]") == [Prim(lib._CFFI_PRIM_INT),
                                   NoOp(6), Pointer(1),
                                   '->', Func(2), FuncEnd(0), 0,
                                   OpenArray(0)]
    assert parse("int(char(*)(long, short))") == [
        Prim(lib._CFFI_PRIM_INT),
        '->', Func(0), NoOp(6), FuncEnd(0),
        Prim(lib._CFFI_PRIM_CHAR),
        NoOp(7), Pointer(5),
        Func(4), NoOp(11), NoOp(12), FuncEnd(0),
        Prim(lib._CFFI_PRIM_LONG),
        Prim(lib._CFFI_PRIM_SHORT)]

def test_fix_arg_types():
    assert parse("int(char(long, short))") == [
        Prim(lib._CFFI_PRIM_INT),
        '->', Func(0), Pointer(5), FuncEnd(0),
        Prim(lib._CFFI_PRIM_CHAR),
        Func(4), NoOp(9), NoOp(10), FuncEnd(0),
        Prim(lib._CFFI_PRIM_LONG),
        Prim(lib._CFFI_PRIM_SHORT)]
    assert parse("int(char[])") == [
        Prim(lib._CFFI_PRIM_INT),
        '->', Func(0), Pointer(4), FuncEnd(0),
        Prim(lib._CFFI_PRIM_CHAR),
        OpenArray(4)]
