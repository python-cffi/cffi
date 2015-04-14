import re
import os
import py
import cffi

r_macro = re.compile(r"#define \w+[(][^\n]*|#include [^\n]*")
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

struct_names = ["bar_s", "foo", "foo_", "foo_s", "foo_s1", "foo_s12"]
assert struct_names == sorted(struct_names)

identifier_names = ["id", "id0", "id05", "id05b", "tail"]
assert identifier_names == sorted(identifier_names)

ctx = ffi.new("struct _cffi_type_context_s *")
c_struct_names = [ffi.new("char[]", _n) for _n in struct_names]
ctx_structs = ffi.new("struct _cffi_struct_union_s[]", len(struct_names))
for _i in range(len(struct_names)):
    ctx_structs[_i].name = c_struct_names[_i]
ctx_structs[3].flags = lib.CT_UNION
ctx.structs_unions = ctx_structs
ctx.num_structs_unions = len(struct_names)

c_identifier_names = [ffi.new("char[]", _n) for _n in identifier_names]
ctx_identifiers = ffi.new("struct _cffi_typename_s[]", len(identifier_names))
for _i in range(len(identifier_names)):
    ctx_identifiers[_i].name = c_identifier_names[_i]
ctx.typenames = ctx_identifiers
ctx.num_typenames = len(identifier_names)


def parse(input):
    out = ffi.new("_cffi_opcode_t[]", 100)
    info = ffi.new("struct _cffi_parse_info_s *")
    info.ctx = ctx
    info.output = out
    info.output_size = len(out)
    for j in range(len(out)):
        out[j] = ffi.cast("void *", -424242)
    res = lib.parse_c_type(info, input)
    if res < 0:
        raise ParseError(ffi.string(info.error_message),
                         info.error_location)
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

def parse_error(input, expected_msg, expected_location):
    e = py.test.raises(ParseError, parse, input)
    assert e.value.args[0] == expected_msg
    assert e.value.args[1] == expected_location

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
Struct = make_getter('STRUCT_UNION')
Typename = make_getter('TYPENAME')


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

def test_error():
    parse_error("short short int", "'short' after another 'short' or 'long'", 6)
    parse_error("long long long", "'long long long' is too long", 10)
    parse_error("short long", "'long' after 'short'", 6)
    parse_error("signed unsigned int", "multiple 'signed' or 'unsigned'", 7)
    parse_error("unsigned signed int", "multiple 'signed' or 'unsigned'", 9)
    parse_error("long char", "invalid combination of types", 5)
    parse_error("short char", "invalid combination of types", 6)
    parse_error("signed void", "invalid combination of types", 7)
    parse_error("unsigned struct", "invalid combination of types", 9)
    #
    parse_error("", "identifier expected", 0)
    parse_error("]", "identifier expected", 0)
    parse_error("*", "identifier expected", 0)
    parse_error("int ]**", "unexpected symbol", 4)
    parse_error("char char", "unexpected symbol", 5)
    parse_error("int(int]", "expected ')'", 7)
    parse_error("int(*]", "expected ')'", 5)
    parse_error("int(]", "identifier expected", 4)
    parse_error("int[?]", "expected a positive integer constant", 4)
    parse_error("int[24)", "expected ']'", 6)
    parse_error("struct", "struct or union name expected", 6)
    parse_error("struct 24", "struct or union name expected", 7)
    parse_error("int[5](*)", "unexpected symbol", 6)
    parse_error("int a(*)", "identifier expected", 6)
    parse_error("int[123456789012345678901234567890]", "number too large", 4)

def test_complexity_limit():
    parse_error("int" + "[]" * 2500, "internal type complexity limit reached",
                202)

def test_struct():
    for i in range(len(struct_names)):
        if i == 3:
            tag = "union"
        else:
            tag = "struct"
        assert parse("%s %s" % (tag, struct_names[i])) == ['->', Struct(i)]
        assert parse("%s %s*" % (tag, struct_names[i])) == [Struct(i),
                                                            '->', Pointer(0)]

def test_identifier():
    for i in range(len(identifier_names)):
        assert parse("%s" % (identifier_names[i])) == ['->', Typename(i)]
        assert parse("%s*" % (identifier_names[i])) == [Typename(i),
                                                        '->', Pointer(0)]
