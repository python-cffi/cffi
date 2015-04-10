

typedef void *_cffi_opcode_t;

#define _CFFI_OP(opcode, arg)   (_cffi_opcode_t)(opcode | (((unsigned long)(arg)) << 8))
#define _CFFI_GETOP(cffi_opcode)    ((unsigned char)(unsigned long)cffi_opcode)
#define _CFFI_GETARG(cffi_opcode)   (((unsigned long)cffi_opcode) >> 8)

#define _CFFI_OP_PRIMITIVE       1
#define _CFFI_OP_POINTER         3
#define _CFFI_OP_ARRAY           5
#define _CFFI_OP_OPEN_ARRAY      7
#define _CFFI_OP_STRUCT_UNION    9
#define _CFFI_OP_ENUM           11
#define _CFFI_OP_TYPENAME       13
#define _CFFI_OP_FUNCTION       15
#define _CFFI_OP_FUNCTION_END   17
#define _CFFI_OP_NOOP           19

#define _CFFI_PRIM_VOID          0
#define _CFFI_PRIM_BOOL          1
#define _CFFI_PRIM_CHAR          2
#define _CFFI_PRIM_SCHAR         3
#define _CFFI_PRIM_UCHAR         4
#define _CFFI_PRIM_SHORT         5
#define _CFFI_PRIM_USHORT        6
#define _CFFI_PRIM_INT           7
#define _CFFI_PRIM_UINT          8
#define _CFFI_PRIM_LONG          9
#define _CFFI_PRIM_ULONG        10
#define _CFFI_PRIM_LONGLONG     11
#define _CFFI_PRIM_ULONGLONG    12
#define _CFFI_PRIM_FLOAT        13
#define _CFFI_PRIM_DOUBLE       14
#define _CFFI_PRIM_LONGDOUBLE   15


struct _cffi_global_s {
    const char *name;
    void *address;
    int type_index;
};

struct _cffi_constant_s {
    const char *name;
    unsigned long long value;
    int type_index_or_plain;
};
#define _CFFI_PLAIN_POSITIVE_INT     (-1)
#define _CFFI_PLAIN_NONPOSITIVE_INT  (-2)

struct _cffi_struct_union_s {
    const char *name;
    size_t size;
    int alignment;
    int flags;               // CT_UNION?  CT_IS_OPAQUE?
    int num_fields;
    int first_field_index;   // -> _cffi_fields array
};

struct _cffi_field_s {
    const char *name;
    size_t field_offset;
    size_t field_size;
    int field_bit_size;
    int field_type;          // -> _cffi_types
};

struct _cffi_enum_s {
    const char *name;
    int integer_type;        // -> _cffi_types
};

struct _cffi_typename_s {
    const char *name;
    int type_index;          // -> _cffi_types
};

struct _cffi_type_context_s {
    const struct _cffi_global_s *globals;
    const struct _cffi_constant_s *constants;
    const struct _cffi_struct_union_s *structs_unions;
    const struct _cffi_field_s *fields;
    const struct _cffi_enum_s *enums;
    const struct _cffi_typename_s *typenames;
    int num_globals;
    int num_constants;
    int num_structs_unions;
    int num_enums;
    int num_typenames;
};

struct _cffi_parse_info_s {
    struct _cffi_type_context_s *ctx;
    _cffi_opcode_t *output;
    int output_size;
    const char **error_location;
    const char **error_message;
};

int parse_c_type(struct _cffi_parse_info_s *info, const char *input);
