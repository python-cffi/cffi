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
    enum token_e kind;
    const char *p, **error_location, **error_message;
    size_t size;
    ctype_opcode_t *opcodes, *opcodes_end;
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

static void parse_error(token_t *tok, const char *msg)
{
    if (tok->kind != TOK_ERROR) {
        tok->kind = TOK_ERROR;
        if (tok->error_location)
            *tok->error_location = tok->p;
        if (tok->error_message)
            *tok->error_message = msg;
    }
}

static ctype_opcode_t *alloc_ds(token_t *tok, size_t num)
{
    ctype_opcode_t *result = tok->opcodes;
    if (num > tok->opcodes_end - result) {
        parse_error(tok, "type too lengthy");
        return NULL;
    }
    tok->opcodes += num;
    return result;
}

#if 0
static void parse_complete(token_t *tok, _crx_qual_type *result);

static void parse_sequel(token_t *tok, intptr_t ds_end)
{
    intptr_t *ds;
    while (tok->kind == TOK_STAR || tok->kind == TOK_CONST ||
           tok->kind == TOK_VOLATILE) {
        ds = alloc_ds(tok, 1);
        if (ds == NULL)
            return;
        ds[0] = tok->kind;
        next_token(tok);
    }

    int check_for_grouping = -1;
    if (tok->kind == TOK_IDENTIFIER) {
        next_token(tok);    /* skip a potential variable name */
        check_for_grouping = 1;
    }

    intptr_t *jump_slot = alloc_ds(tok, 1);
    if (jump_slot == NULL)
        return;
    *jump_slot = ds_end;

 next_right_part:
    check_for_grouping++;

    switch (tok->kind) {

    case TOK_OPEN_PAREN:
        next_token(tok);

        if (check_for_grouping == 0 && (tok->kind == TOK_STAR ||
                                        tok->kind == TOK_CONST ||
                                        tok->kind == TOK_VOLATILE ||
                                        tok->kind == TOK_OPEN_BRACKET)) {
            /* just parentheses for grouping */
            ds = tok->delay_slots;
            parse_sequel(tok, *jump_slot);
            *jump_slot = -(ds - tok->all_delay_slots);
        }
        else {
            /* function type */
            ds = alloc_ds(tok, 2);
            if (ds == NULL)
                return;
            ds[0] = TOK_OPEN_PAREN;
            ds[1] = 0;
            if (tok->kind == TOK_VOID && get_following_char(tok) == ')') {
                next_token(tok);
            }
            if (tok->kind != TOK_CLOSE_PAREN) {
                while (1) {
                    if (tok->kind == TOK_DOTDOTDOT) {
                        ds[0] = TOK_DOTDOTDOT;
                        next_token(tok);
                        break;
                    }
                    intptr_t *ds_type = alloc_ds(tok, 2);
                    if (ds_type == NULL)
                        return;
                    assert(ds_type == ds + 2 + 2 * ds[1]);
                    assert(2 * sizeof(intptr_t) >= sizeof(_crx_qual_type));
                    parse_complete(tok, (_crx_qual_type *)ds_type);
                    ds[1]++;
                    if (tok->kind != TOK_COMMA)
                        break;
                    next_token(tok);
                }
            }
            intptr_t *ds_next = alloc_ds(tok, 1);
            if (ds_next == NULL)
                return;
            assert(ds_next == ds + 2 + 2 * ds[1]);
            *ds_next = *jump_slot;
            *jump_slot = -(ds - tok->all_delay_slots);
        }

        if (tok->kind != TOK_CLOSE_PAREN) {
            parse_error(tok, "expected ')'");
            return;
        }
        next_token(tok);
        goto next_right_part;

    case TOK_OPEN_BRACKET:
    {
        uintptr_t length = (uintptr_t)-1;
        next_token(tok);
        if (tok->kind != TOK_CLOSE_BRACKET) {
            if (tok->kind != TOK_INTEGER) {
                parse_error(tok, "expected a positive integer constant");
                return;
            }

            if (sizeof(uintptr_t) > sizeof(unsigned long))
                length = strtoull(tok->p, NULL, 10);
            else
                length = strtoul(tok->p, NULL, 10);
            if (length == (uintptr_t)-1) {
                parse_error(tok, "number too large");
                return;
            }
            next_token(tok);
        }

        if (tok->kind != TOK_CLOSE_BRACKET) {
            parse_error(tok, "expected ']'");
            return;
        }
        next_token(tok);

        ds = alloc_ds(tok, 3);
        if (ds == NULL)
            return;
        ds[0] = TOK_OPEN_BRACKET;
        ds[1] = (intptr_t)length;
        ds[2] = *jump_slot;
        *jump_slot = -(ds - tok->all_delay_slots);
        goto next_right_part;
    }
    default:
        break;
    }
}
#endif

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

static void parse_complete(token_t *tok)
{
    int const_qualifier = 0, volatile_qualifier = 0;

 qualifiers:
    switch (tok->kind) {
    case TOK_CONST:
        const_qualifier = 1;
        next_token(tok);
        goto qualifiers;
    case TOK_VOLATILE:
        volatile_qualifier = 1;
        next_token(tok);
        goto qualifiers;
    default:
        ;
    }

    int t1;
    int modifiers_length = 0;
    int modifiers_sign = 0;
 modifiers:
    switch (tok->kind) {

    case TOK_SHORT:
        if (modifiers_length != 0) {
            parse_error(tok, "'short' after another 'short' or 'long'");
            return;
        }
        modifiers_length--;
        next_token(tok);
        goto modifiers;

    case TOK_LONG:
        if (modifiers_length < 0) {
            parse_error(tok, "'long' after 'short'");
            return;
        }
        if (modifiers_length >= 2) {
            parse_error(tok, "'long long long' is too long");
            return;
        }
        modifiers_length++;
        next_token(tok);
        goto modifiers;

    case TOK_SIGNED:
        if (modifiers_sign) {
            parse_error(tok, "multiple 'signed' or 'unsigned'");
            return;
        }
        modifiers_sign++;
        next_token(tok);
        goto modifiers;

    case TOK_UNSIGNED:
        if (modifiers_sign) {
            parse_error(tok, "multiple 'signed' or 'unsigned'");
            return;
        }
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
            parse_error(tok, "invalid combination of types");
            return;

        case TOK_DOUBLE:
            if (modifiers_sign != 0 || modifiers_length != 1) {
                parse_error(tok, "invalid combination of types");
                return;
            }
            next_token(tok);
            t1 = CTOP_LONGDOUBLE;
            break;

        case TOK_CHAR:
            if (modifiers_length != 0) {
                parse_error(tok, "invalid combination of types");
                return;
            }
            modifiers_length = -2;
            /* fall-through */
        case TOK_INT:
            next_token(tok);
            /* fall-through */
        default:
            if (modifiers_sign >= 0)
                switch (modifiers_length) {
                case -2: t1 = CTOP_SCHAR; break;
                case -1: t1 = CTOP_SHORT; break;
                case 1:  t1 = CTOP_LONG; break;
                case 2:  t1 = CTOP_LONGLONG; break;
                default: t1 = CTOP_INT; break;
                }
            else
                switch (modifiers_length) {
                case -2: t1 = CTOP_UCHAR; break;
                case -1: t1 = CTOP_USHORT; break;
                case 1:  t1 = CTOP_ULONG; break;
                case 2:  t1 = CTOP_ULONGLONG; break;
                default: t1 = CTOP_UINT; break;
                }
        }
    }
    else {
        switch (tok->kind) {
        case TOK_INT:
            t1 = CTOP_INT;
            break;
        case TOK_CHAR:
            t1 = CTOP_CHAR;
            break;
        case TOK_VOID:
            t1 = CTOP_VOID;
            break;
        case TOK__BOOL:
            t1 = CTOP_BOOL;
            break;
        case TOK_FLOAT:
            t1 = CTOP_FLOAT;
            break;
        case TOK_DOUBLE:
            t1 = CTOP_DOUBLE;
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
            parse_error(tok, "identifier expected");
            return;
        }
        next_token(tok);
    }
    *alloc_ds(tok, 1) = t1;
    if (const_qualifier)
        *alloc_ds(tok, 1) = CTOP_CONST;
    if (volatile_qualifier)
        *alloc_ds(tok, 1) = CTOP_VOLATILE;

    //parse_sequel(tok, CTOP_END);
    *alloc_ds(tok, 1) = CTOP_END;
}


int parse_c_type(const char *input,
                 ctype_opcode_t *output, size_t output_size,
                 const char **error_loc, const char **error_msg)
{
    token_t token;

    token.kind = TOK_START;
    token.p = input;
    token.error_location = error_loc;
    token.error_message = error_msg;
    token.size = 0;
    token.opcodes = output;
    token.opcodes_end = output + output_size;
    next_token(&token);
    parse_complete(&token);

    if (token.kind != TOK_END) {
        parse_error(&token, "unexpected symbol");
        return -1;
    }
    return 0;
}
