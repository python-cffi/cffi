#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include "parse_c_type.h"


enum token_e {
    TOK_STAR='*',
    TOK_OPEN_PAREN='(',
    TOK_CLOSE_PAREN=')',
    TOK_OPEN_BRACKET='[',
    TOK_CLOSE_BRACKET=']',
    TOK_COMMA=',',

    TOK_START=256,
    TOK_END,
    TOK_ERROR,
    TOK_IDENTIFIER,
    TOK_INTEGER,
    TOK_DOTDOTDOT,

    /* keywords */
    TOK__BOOL,
    TOK_CHAR,
    //TOK__COMPLEX,
    TOK_CONST,
    TOK_DOUBLE,
    TOK_FLOAT,
    //TOK__IMAGINARY,
    TOK_INT,
    TOK_LONG,
    TOK_SHORT,
    TOK_SIGNED,
    TOK_STRUCT,
    TOK_UNION,
    TOK_UNSIGNED,
    TOK_VOID,
    TOK_VOLATILE,
};

typedef struct {
    struct _cffi_parse_info_s *info;
    const char *input, *p;
    size_t size;              // the next token is at 'p' and of length 'size'
    enum token_e kind;
    _cffi_opcode_t *output;
    size_t output_index;
} token_t;

static int is_space(char x)
{
    return (x == ' ' || x == '\f' || x == '\n' || x == '\r' ||
            x == '\t' || x == '\v');
}

static int is_ident_first(char x)
{
    return (('A' <= x && x <= 'Z') || ('a' <= x && x <= 'z') || x == '_');
}

static int is_digit(char x)
{
    return ('0' <= x && x <= '9');
}

static int is_ident_next(char x)
{
    return (is_ident_first(x) || is_digit(x));
}

static char get_following_char(token_t *tok)
{
    const char *p = tok->p + tok->size;
    if (tok->kind == TOK_ERROR)
        return 0;
    while (is_space(*p))
        p++;
    return *p;
}

static int number_of_commas(token_t *tok)
{
    const char *p = tok->p;
    int result = 0;
    int nesting = 0;
    while (1) {
        switch (*p++) {
        case ',': result += !nesting; break;
        case '(': nesting++; break;
        case ')': if ((--nesting) < 0) return result; break;
        case 0:   return result;
        default:  break;
        }
    }
}

static void next_token(token_t *tok)
{
    const char *p = tok->p + tok->size;
    if (tok->kind == TOK_ERROR)
        return;
    while (!is_ident_first(*p)) {
        if (is_space(*p)) {
            p++;
        }
        else if (is_digit(*p)) {
            tok->kind = TOK_INTEGER;
            tok->p = p;
            tok->size = 1;
            while (is_digit(p[tok->size]))
                tok->size++;
            return;
        }
        else if (p[0] == '.' && p[1] == '.' && p[2] == '.') {
            tok->kind = TOK_DOTDOTDOT;
            tok->p = p;
            tok->size = 3;
            return;
        }
        else if (*p) {
            tok->kind = *p;
            tok->p = p;
            tok->size = 1;
            return;
        }
        else {
            tok->kind = TOK_END;
            tok->p = p;
            tok->size = 0;
            return;
        }
    }
    tok->kind = TOK_IDENTIFIER;
    tok->p = p;
    tok->size = 1;
    while (is_ident_next(p[tok->size]))
        tok->size++;

    switch (*p) {
    case '_':
        if (tok->size == 5 && !memcmp(p, "_Bool", 5))  tok->kind = TOK__BOOL;
        break;
    case 'c':
        if (tok->size == 4 && !memcmp(p, "char", 4))   tok->kind = TOK_CHAR;
        if (tok->size == 5 && !memcmp(p, "const", 5))  tok->kind = TOK_CONST;
        break;
    case 'd':
        if (tok->size == 6 && !memcmp(p, "double", 6)) tok->kind = TOK_DOUBLE;
        break;
    case 'f':
        if (tok->size == 5 && !memcmp(p, "float", 5))  tok->kind = TOK_FLOAT;
        break;
    case 'i':
        if (tok->size == 3 && !memcmp(p, "int", 3))    tok->kind = TOK_INT;
        break;
    case 'l':
        if (tok->size == 4 && !memcmp(p, "long", 4))   tok->kind = TOK_LONG;
        break;
    case 's':
        if (tok->size == 5 && !memcmp(p, "short", 5))  tok->kind = TOK_SHORT;
        if (tok->size == 6 && !memcmp(p, "signed", 6)) tok->kind = TOK_SIGNED;
        if (tok->size == 6 && !memcmp(p, "struct", 6)) tok->kind = TOK_STRUCT;
        break;
    case 'u':
        if (tok->size == 5 && !memcmp(p, "union", 5))  tok->kind = TOK_UNION;
        if (tok->size == 8 && !memcmp(p,"unsigned",8)) tok->kind = TOK_UNSIGNED;
        break;
    case 'v':
        if (tok->size == 4 && !memcmp(p, "void", 4))   tok->kind = TOK_VOID;
        if (tok->size == 8 && !memcmp(p,"volatile",8)) tok->kind = TOK_VOLATILE;
        break;
    }
}

static int parse_error(token_t *tok, const char *msg)
{
    if (tok->kind != TOK_ERROR) {
        tok->kind = TOK_ERROR;
        tok->info->error_location = tok->p - tok->input;
        tok->info->error_message = msg;
    }
    return -1;
}

static int write_ds(token_t *tok, _cffi_opcode_t ds)
{
    size_t index = tok->output_index;
    if (index >= tok->info->output_size) {
        parse_error(tok, "internal type complexity limit reached");
        return -1;
    }
    tok->output[index] = ds;
    tok->output_index = index + 1;
    return index;
}

static int parse_complete(token_t *tok);

static int parse_sequel(token_t *tok, int outer)
{
    /* Emit opcodes for the "sequel", which is the optional part of a
       type declaration that follows the type name, i.e. everything
       with '*', '[ ]', '( )'.  Returns the entry point index pointing
       the innermost opcode (the one that corresponds to the complete
       type).  The 'outer' argument is the index of the opcode outside
       this "sequel".
     */

 header:
    switch (tok->kind) {
    case TOK_STAR:
        outer = write_ds(tok, _CFFI_OP(_CFFI_OP_POINTER, outer));
        next_token(tok);
        goto header;
    case TOK_CONST:
        /* ignored for now */
        next_token(tok);
        goto header;
    case TOK_VOLATILE:
        /* ignored for now */
        next_token(tok);
        goto header;
    default:
        break;
    }

    int check_for_grouping = 1;
    if (tok->kind == TOK_IDENTIFIER) {
        next_token(tok);    /* skip a potential variable name */
        check_for_grouping = 0;
    }

    _cffi_opcode_t result = 0;
    _cffi_opcode_t *p_current = &result;

    while (tok->kind == TOK_OPEN_PAREN) {
        next_token(tok);

        if ((check_for_grouping--) == 1 && (tok->kind == TOK_STAR ||
                                            tok->kind == TOK_CONST ||
                                            tok->kind == TOK_VOLATILE ||
                                            tok->kind == TOK_OPEN_BRACKET)) {
            /* just parentheses for grouping.  Use a OP_NOOP to simplify */
            int x;
            assert(p_current == &result);
            x = tok->output_index;
            p_current = tok->output + x;

            write_ds(tok, _CFFI_OP(_CFFI_OP_NOOP, 0));

            x = parse_sequel(tok, x);
            result = _CFFI_OP(_CFFI_GETOP(0), x);
        }
        else {
            /* function type */
            int arg_total, base_index, arg_next, has_ellipsis=0;

            if (tok->kind == TOK_VOID && get_following_char(tok) == ')') {
                next_token(tok);
            }

            /* (over-)estimate 'arg_total'.  May return 1 when it is really 0 */
            arg_total = number_of_commas(tok) + 1;

            *p_current = _CFFI_OP(_CFFI_GETOP(*p_current), tok->output_index);
            p_current = tok->output + tok->output_index;

            base_index = write_ds(tok, _CFFI_OP(_CFFI_OP_FUNCTION, 0));
            if (base_index < 0)
                return -1;
            /* reserve (arg_total + 1) slots for the arguments and the
               final FUNCTION_END */
            for (arg_next = 0; arg_next <= arg_total; arg_next++)
                if (write_ds(tok, _CFFI_OP(0, 0)) < 0)
                    return -1;

            arg_next = base_index + 1;

            if (tok->kind != TOK_CLOSE_PAREN) {
                while (1) {
                    if (tok->kind == TOK_DOTDOTDOT) {
                        has_ellipsis = 1;
                        next_token(tok);
                        break;
                    }
                    int arg = parse_complete(tok);
                    _cffi_opcode_t oarg;
                    switch (_CFFI_GETOP(tok->output[arg])) {
                    case _CFFI_OP_ARRAY:
                    case _CFFI_OP_OPEN_ARRAY:
                        arg = _CFFI_GETARG(tok->output[arg]);
                        /* fall-through */
                    case _CFFI_OP_FUNCTION:
                        oarg = _CFFI_OP(_CFFI_OP_POINTER, arg);
                        break;
                    default:
                        oarg = _CFFI_OP(_CFFI_OP_NOOP, arg);
                        break;
                    }
                    assert(arg_next - base_index <= arg_total);
                    tok->output[arg_next++] = oarg;
                    if (tok->kind != TOK_COMMA)
                        break;
                    next_token(tok);
                }
            }
            tok->output[arg_next] = _CFFI_OP(_CFFI_OP_FUNCTION_END,
                                             has_ellipsis);
        }

        if (tok->kind != TOK_CLOSE_PAREN)
            return parse_error(tok, "expected ')'");
        next_token(tok);
    }

    while (tok->kind == TOK_OPEN_BRACKET) {
        *p_current = _CFFI_OP(_CFFI_GETOP(*p_current), tok->output_index);
        p_current = tok->output + tok->output_index;

        next_token(tok);
        if (tok->kind != TOK_CLOSE_BRACKET) {
            size_t length;

            if (tok->kind != TOK_INTEGER)
                return parse_error(tok, "expected a positive integer constant");

            errno = 0;
            if (sizeof(length) > sizeof(unsigned long))
                length = strtoull(tok->p, NULL, 10);
            else
                length = strtoul(tok->p, NULL, 10);
            if (errno == ERANGE || ((ssize_t)length) < 0)
                return parse_error(tok, "number too large");
            next_token(tok);

            write_ds(tok, _CFFI_OP(_CFFI_OP_ARRAY, 0));
            write_ds(tok, (_cffi_opcode_t)length);
        }
        else
            write_ds(tok, _CFFI_OP(_CFFI_OP_OPEN_ARRAY, 0));

        if (tok->kind != TOK_CLOSE_BRACKET)
            return parse_error(tok, "expected ']'");
        next_token(tok);
    }

    *p_current = _CFFI_OP(_CFFI_GETOP(*p_current), outer);
    return _CFFI_GETARG(result);
}


#define MAKE_SEARCH_FUNC(FIELD)                                 \
  int search_in_##FIELD(const struct _cffi_type_context_s *ctx, \
                        const char *search, size_t search_len)  \
  {                                                             \
      int left = 0, right = ctx->num_##FIELD;                   \
                                                                \
      while (left < right) {                                    \
          int middle = (left + right) / 2;                      \
          const char *src = ctx->FIELD[middle].name;            \
          int diff = strncmp(src, search, search_len);          \
          if (diff == 0 && src[search_len] == '\0')             \
              return middle;                                    \
          else if (diff >= 0)                                   \
              right = middle;                                   \
          else                                                  \
              left = middle + 1;                                \
      }                                                         \
      return -1;                                                \
  }

MAKE_SEARCH_FUNC(globals)
MAKE_SEARCH_FUNC(structs_unions)
MAKE_SEARCH_FUNC(typenames)

#undef MAKE_SEARCH_FUNC


static int parse_complete(token_t *tok)
{
 qualifiers:
    switch (tok->kind) {
    case TOK_CONST:
        /* ignored for now */
        next_token(tok);
        goto qualifiers;
    case TOK_VOLATILE:
        /* ignored for now */
        next_token(tok);
        goto qualifiers;
    default:
        ;
    }

    unsigned int t0;
    _cffi_opcode_t t1;
    int modifiers_length = 0;
    int modifiers_sign = 0;
 modifiers:
    switch (tok->kind) {

    case TOK_SHORT:
        if (modifiers_length != 0)
            return parse_error(tok, "'short' after another 'short' or 'long'");
        modifiers_length--;
        next_token(tok);
        goto modifiers;

    case TOK_LONG:
        if (modifiers_length < 0)
            return parse_error(tok, "'long' after 'short'");
        if (modifiers_length >= 2)
            return parse_error(tok, "'long long long' is too long");
        modifiers_length++;
        next_token(tok);
        goto modifiers;

    case TOK_SIGNED:
        if (modifiers_sign)
            return parse_error(tok, "multiple 'signed' or 'unsigned'");
        modifiers_sign++;
        next_token(tok);
        goto modifiers;

    case TOK_UNSIGNED:
        if (modifiers_sign)
            return parse_error(tok, "multiple 'signed' or 'unsigned'");
        modifiers_sign--;
        next_token(tok);
        goto modifiers;

    default:
        break;
    }

    if (modifiers_length || modifiers_sign) {

        switch (tok->kind) {

        case TOK_VOID:
        case TOK__BOOL:
        case TOK_FLOAT:
        case TOK_STRUCT:
        case TOK_UNION:
            return parse_error(tok, "invalid combination of types");

        case TOK_DOUBLE:
            if (modifiers_sign != 0 || modifiers_length != 1)
                return parse_error(tok, "invalid combination of types");
            next_token(tok);
            t0 = _CFFI_PRIM_LONGDOUBLE;
            break;

        case TOK_CHAR:
            if (modifiers_length != 0)
                return parse_error(tok, "invalid combination of types");
            modifiers_length = -2;
            /* fall-through */
        case TOK_INT:
            next_token(tok);
            /* fall-through */
        default:
            if (modifiers_sign >= 0)
                switch (modifiers_length) {
                case -2: t0 = _CFFI_PRIM_SCHAR; break;
                case -1: t0 = _CFFI_PRIM_SHORT; break;
                case 1:  t0 = _CFFI_PRIM_LONG; break;
                case 2:  t0 = _CFFI_PRIM_LONGLONG; break;
                default: t0 = _CFFI_PRIM_INT; break;
                }
            else
                switch (modifiers_length) {
                case -2: t0 = _CFFI_PRIM_UCHAR; break;
                case -1: t0 = _CFFI_PRIM_USHORT; break;
                case 1:  t0 = _CFFI_PRIM_ULONG; break;
                case 2:  t0 = _CFFI_PRIM_ULONGLONG; break;
                default: t0 = _CFFI_PRIM_UINT; break;
                }
        }
        t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, t0);
    }
    else {
        switch (tok->kind) {
        case TOK_INT:
            t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_INT);
            break;
        case TOK_CHAR:
            t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_CHAR);
            break;
        case TOK_VOID:
            t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_VOID);
            break;
        case TOK__BOOL:
            t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_BOOL);
            break;
        case TOK_FLOAT:
            t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_FLOAT);
            break;
        case TOK_DOUBLE:
            t1 = _CFFI_OP(_CFFI_OP_PRIMITIVE, _CFFI_PRIM_DOUBLE);
            break;
        case TOK_IDENTIFIER:
        {
            int n = search_in_typenames(tok->info->ctx, tok->p, tok->size);
            if (n < 0)
                return parse_error(tok, "undefined type name");

            t1 = _CFFI_OP(_CFFI_OP_TYPENAME, n);
            break;
        }
        case TOK_STRUCT:
        case TOK_UNION:
        {
            int kind = tok->kind;
            next_token(tok);
            if (tok->kind != TOK_IDENTIFIER)
                return parse_error(tok, "struct or union name expected");

            int n = search_in_structs_unions(tok->info->ctx, tok->p, tok->size);
            if (n < 0)
                return parse_error(tok, "undefined struct/union name");
            if (((tok->info->ctx->structs_unions[n].flags & CT_UNION) != 0)
                ^ (kind == TOK_UNION))
                return parse_error(tok, "wrong kind of tag: struct vs union");

            t1 = _CFFI_OP(_CFFI_OP_STRUCT_UNION, n);
            break;
        }
        default:
            return parse_error(tok, "identifier expected");
        }
        next_token(tok);
    }

    return parse_sequel(tok, write_ds(tok, t1));
}


int parse_c_type(struct _cffi_parse_info_s *info, const char *input)
{
    int result;
    token_t token;

    token.info = info;
    token.kind = TOK_START;
    token.input = input;
    token.p = input;
    token.size = 0;
    token.output = info->output;
    token.output_index = 0;

    next_token(&token);
    result = parse_complete(&token);

    if (token.kind != TOK_END)
        return parse_error(&token, "unexpected symbol");
    return result;
}
