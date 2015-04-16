
class CffiOp(object):
    def __init__(self, op, arg):
        self.op = op
        self.arg = arg
    def as_c_expr(self):
        if self.op is None:
            assert isinstance(self.arg, str)
            return '(_cffi_opcode_t)(%s)' % (self.arg,)
        classname = CLASS_NAME[self.op]
        return '_CFFI_OP(_CFFI_OP_%s, %d)' % (classname, self.arg)
    def __str__(self):
        classname = CLASS_NAME.get(self.op, self.op)
        return '(%s %s)' % (classname, self.arg)

OP_PRIMITIVE       = 1
OP_POINTER         = 3
OP_ARRAY           = 5
OP_OPEN_ARRAY      = 7
OP_STRUCT_UNION    = 9
OP_ENUM            = 11
OP_FUNCTION        = 13
OP_FUNCTION_END    = 15
OP_NOOP            = 17
OP_BITFIELD        = 19
OP_TYPENAME        = 21
OP_CPYTHON_BLTN_V  = 23   # varargs
OP_CPYTHON_BLTN_N  = 25   # noargs
OP_CPYTHON_BLTN_O  = 27   # O  (i.e. a single arg)
OP_CONSTANT        = 29
OP_CONSTANT_INT    = 31
OP_GLOBAL_VAR      = 33

PRIM_VOID          = 0
PRIM_BOOL          = 1
PRIM_CHAR          = 2
PRIM_SCHAR         = 3
PRIM_UCHAR         = 4
PRIM_SHORT         = 5
PRIM_USHORT        = 6
PRIM_INT           = 7
PRIM_UINT          = 8
PRIM_LONG          = 9
PRIM_ULONG         = 10
PRIM_LONGLONG      = 11
PRIM_ULONGLONG     = 12
PRIM_FLOAT         = 13
PRIM_DOUBLE        = 14
PRIM_LONGDOUBLE    = 15

PRIM_WCHAR         = 16
PRIM_INT8          = 17
PRIM_UINT8         = 18
PRIM_INT16         = 19
PRIM_UINT16        = 20
PRIM_INT32         = 21
PRIM_UINT32        = 22
PRIM_INT64         = 23
PRIM_UINT64        = 24
PRIM_INTPTR        = 25
PRIM_UINTPTR       = 26
PRIM_PTRDIFF       = 27
PRIM_SIZE          = 28
PRIM_SSIZE         = 29

_NUM_PRIM          = 30

PRIMITIVE_TO_INDEX = {
    'char':               PRIM_CHAR,
    'short':              PRIM_SHORT,
    'int':                PRIM_INT,
    'long':               PRIM_LONG,
    'long long':          PRIM_LONGLONG,
    'signed char':        PRIM_SCHAR,
    'unsigned char':      PRIM_UCHAR,
    'unsigned short':     PRIM_USHORT,
    'unsigned int':       PRIM_UINT,
    'unsigned long':      PRIM_ULONG,
    'unsigned long long': PRIM_ULONGLONG,
    'float':              PRIM_FLOAT,
    'double':             PRIM_DOUBLE,
    'long double':        PRIM_LONGDOUBLE,
    '_Bool':              PRIM_BOOL,
    'wchar_t':            PRIM_WCHAR,
    'int8_t':             PRIM_INT8,
    'uint8_t':            PRIM_UINT8,
    'int16_t':            PRIM_INT16,
    'uint16_t':           PRIM_UINT16,
    'int32_t':            PRIM_INT32,
    'uint32_t':           PRIM_UINT32,
    'int64_t':            PRIM_INT64,
    'uint64_t':           PRIM_UINT64,
    'intptr_t':           PRIM_INTPTR,
    'uintptr_t':          PRIM_UINTPTR,
    'ptrdiff_t':          PRIM_PTRDIFF,
    'size_t':             PRIM_SIZE,
    'ssize_t':            PRIM_SSIZE,
    }

CLASS_NAME = {}
for _name, _value in globals().items():
    if _name.startswith('OP_') and isinstance(_value, int):
        CLASS_NAME[_value] = _name[3:]
