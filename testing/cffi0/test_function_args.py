import pytest
try:
    from hypothesis import given
    from hypothesis import strategies as st
except ImportError as e:
    def test_types():
        pytest.skip(str(e))
else:

    from cffi import FFI
    import random

    ALL_PRIMITIVES = [
        'unsigned char',
        'short',
        'int',
        'long',
        'long long',
        'float',
        'double',
        'long double',
    ]
    def _make_struct(s):
        return st.lists(s, min_size=1)
    types = st.recursive(st.sampled_from(ALL_PRIMITIVES), _make_struct)

    def draw_primitive(ffi, typename):
        value = random.random() * 2**40
        if typename != 'long double':
            return ffi.cast(typename, value)
        else:
            return value


    @given(st.lists(types), types)
    def test_types(tp_args, tp_result):
        cdefs = []
        structs = {}

        def build_type(tp):
            if type(tp) is list:
                field_types = [build_type(tp1) for tp1 in tp]
                fields = ['%s f%d;' % (ftp, j)
                          for (j, ftp) in enumerate(field_types)]
                fields = '\n    '.join(fields)
                name = 's%d' % len(cdefs)
                cdefs.append("typedef struct {\n    %s\n} %s;" % (fields, name))
                structs[name] = field_types
                return name
            else:
                return tp

        args = [build_type(tp) for tp in tp_args]
        result = build_type(tp_result)

        ffi = FFI()
        ffi.cdef("\n".join(cdefs))

        def make_arg(tp):
            if tp in structs:
                return [make_arg(tp1) for tp1 in structs[tp]]
            else:
                return draw_primitive(ffi, tp)

        passed_args = [make_arg(arg) for arg in args]
        returned_value = make_arg(result)
        received_arguments = []

        _tp_long_double = ffi.typeof("long double")
        def expand(value):
            if isinstance(value, ffi.CData):
                t = ffi.typeof(value)
                if t is _tp_long_double:
                    return float(ffi.cast("double", value))
                return [expand(getattr(value, 'f%d' % i))
                        for i in range(len(t.fields))]
            else:
                return value

        def callback(*args):
            received_arguments.append([expand(arg) for arg in args])
            return returned_value

        fptr = ffi.callback("%s(*)(%s)" % (result, ','.join(args)), callback)
        received_return = fptr(*passed_args)

        assert len(received_arguments) == 1
        assert passed_args == received_arguments[0]
        assert expand(received_return) == returned_value
