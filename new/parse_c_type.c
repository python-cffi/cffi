#include <stdlib.h>
#include <assert.h>
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
    const char *p;
    enum token_e kind;
    size_t size;
    _cffi_opcode_t *output;
    unsigned long output_index;
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
        if (tok->info->error_location)
            *tok->info->error_location = tok->p;
        if (tok->info->error_message)
            *tok->info->error_message = msg;
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
                    assert(arg_next - base_index <= arg_total);
                    tok->output[arg_next++] = _CFFI_OP(_CFFI_OP_NOOP, arg);
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

            if (sizeof(length) > sizeof(unsigned long))
                length = strtoull(tok->p, NULL, 10);
            else
                length = strtoul(tok->p, NULL, 10);
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

#if 0
static void fetch_delay_slots(token_t *tok, _crx_qual_type *result,
                              intptr_t *delay_slot)
{
    if (tok->kind == TOK_ERROR)
        return;
    tok->delay_slots = delay_slot;
    while (1) {
        intptr_t tok_kind = *delay_slot++;
        if (tok_kind <= 0) {
            delay_slot = tok->all_delay_slots + (-tok_kind);
            continue;
        }
        switch (tok_kind) {
        case TOK_END:
            return;    /* done */
        case TOK_STAR:
            result->type = tok->cb->get_pointer_type(tok->cb, result->type,
                                                     result->qualifiers);
            result->qualifiers = 0;
            break;
        case TOK_CONST:
            result->qualifiers |= _CRX_CONST;
            break;
        case TOK_VOLATILE:
            result->qualifiers |= _CRX_VOLATILE;
            break;
        case TOK_OPEN_BRACKET:   /* array */
            {
                uintptr_t length = (uintptr_t)*delay_slot++;
                if (length != (uintptr_t)-1)
                    result->type = tok->cb->get_array_type(
                        tok->cb, result->type, length);
                else
                    result->type = tok->cb->get_incomplete_array_type(
                        tok->cb, result->type);
                /* result->qualifiers remains unmodified */
                break;
            }
        case TOK_OPEN_PAREN:   /* function */
        case TOK_DOTDOTDOT:    /* function ending with a '...' */
            {
                intptr_t nbargs = *delay_slot++;
                _crx_type_t *t1;
                _crx_qual_type *argtypes = (_crx_qual_type *)delay_slot;
                delay_slot += 2 * nbargs;
                if (tok_kind == TOK_DOTDOTDOT)
                    t1 = tok->cb->get_ellipsis_function_type(tok->cb,
                                                             result->type,
                                                             argtypes, nbargs);
                else
                    t1 = tok->cb->get_function_type(tok->cb, result->type,
                                                    argtypes, nbargs, NULL);
                result->type = t1;
                result->qualifiers = 0; /* drop qualifiers on the return type */
                break;
            }
        default:
            assert(!"missing delay slot case");
        }
    }
}
#endif

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
            abort();
#if 0
            _crx_qual_type qt2;
            char identifier[1024];
            if (tok->size >= 1024) {
                parse_error(tok, "identifier name too long");
                return;
            }
            memcpy(identifier, tok->p, tok->size);
            identifier[tok->size] = 0;
            qt2 = tok->cb->get_user_type(tok->cb, identifier);
            t1 = qt2.type;
            result->qualifiers |= qt2.qualifiers;
            break;
#endif
        }
        case TOK_STRUCT:
        case TOK_UNION:
        {
            abort();
#if 0
            char identifier[1024];
            int kind = tok->kind;
            next_token(tok);
            if (tok->kind != TOK_IDENTIFIER) {
                parse_error(tok, "struct or union name expected");
                return;
            }
            if (tok->size >= 1024) {
                parse_error(tok, "struct or union name too long");
                return;
            }
            memcpy(identifier, tok->p, tok->size);
            identifier[tok->size] = 0;
            if (kind == TOK_STRUCT)
                t1 = tok->cb->get_struct_type(tok->cb, identifier);
            else
                t1 = tok->cb->get_union_type(tok->cb, identifier);
            break;
#endif
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
