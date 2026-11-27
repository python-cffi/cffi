import io
import pytest

from cffi import FFI, recompiler
from testing.cffi0.test_parsing import FakeBackend


def _emit_c_source(cdef_src, module_name="testmod", preamble=""):
    ffi = FFI(backend=FakeBackend())
    ffi.cdef(cdef_src)
    recomp = recompiler.Recompiler(ffi, module_name)
    recomp.collect_type_table()
    recomp.collect_step_tables()
    buf = io.StringIO()
    recomp.write_source_to_f(buf, preamble)
    return buf.getvalue()


def test_nested_anonymous_partial_struct():
    c_src = _emit_c_source("""
        struct a {
            struct {
                ...;
            } d;
            ...;
        };
    """)
    assert "sizeof(((struct a *)0)->d)" in c_src
    assert "(size_t)-2" not in c_src


def test_nested_anonymous_partial_struct_with_fields():
    c_src = _emit_c_source("""
        struct a {
            int b;
            struct {
                int c;
                int arr[...];
                ...;
            } d;
        };
    """)
    assert "sizeof(((struct a *)0)->d)" in c_src
    assert "offsetof(struct a, d.c) - offsetof(struct a, d)" in c_src
    assert "sizeof(((struct a *)0)->d.c)" in c_src
    assert "_cffi_array_len(((struct a *)0)->d.arr)" in c_src
    assert "(size_t)-2" not in c_src


def test_deeply_nested_anonymous_partial_union_and_array():
    c_src = _emit_c_source("""
        typedef struct {
            union {
                struct {
                    int x;
                    ...;
                } inner[2];
                ...;
            } mid;
        } outer_t;
    """)
    assert "sizeof(((outer_t *)0)->mid)" in c_src
    assert "sizeof(((outer_t *)0)->mid.inner[0])" in c_src
    assert "offsetof(outer_t, mid.inner[0].x) - offsetof(outer_t, mid.inner[0])" in c_src


def test_unnamed_struct_containing_named_partial_struct():
    c_src = _emit_c_source("""
        struct a {
            struct {
                struct {
                    int x;
                    ...;
                } inner;
            };
            ...;
        };
    """)
    assert "sizeof(((struct a *)0)->inner)" in c_src
    assert "offsetof(struct a, inner.x) - offsetof(struct a, inner)" in c_src
    assert "(size_t)-2" not in c_src


def test_pointer_to_anonymous_partial_struct_still_rejected():
    ffi = FFI(backend=FakeBackend())
    with pytest.raises(NotImplementedError):
        ffi.cdef("""
            struct a {
                struct {
                    ...;
                } *d;
            };
        """)
