

typedef int ctype_opcode_t;

#define CTOP_END         0
#define CTOP_CONST       1
#define CTOP_VOLATILE    2

#define CTOP_VOID        100
#define CTOP_BOOL        101
#define CTOP_CHAR        102
#define CTOP_SCHAR       103
#define CTOP_UCHAR       104
#define CTOP_SHORT       105
#define CTOP_USHORT      106
#define CTOP_INT         107
#define CTOP_UINT        108
#define CTOP_LONG        109
#define CTOP_ULONG       110
#define CTOP_LONGLONG    111
#define CTOP_ULONGLONG   112
#define CTOP_FLOAT       113
#define CTOP_DOUBLE      114
#define CTOP_LONGDOUBLE  115


int parse_c_type(const char *input,
                 ctype_opcode_t *output, size_t output_size,
                 const char **error_loc, const char **error_msg);
