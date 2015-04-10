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

def make_getter(name):
    opcode = getattr(lib, '_CFFI_OP_' + name)
    def getter(value):
        return opcode | (value << 8)
    return getter

Prim = make_getter('PRIMITIVE')
Array = make_getter('ARRAY')
OpenArray = make_getter('OPEN_ARRAY')


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
