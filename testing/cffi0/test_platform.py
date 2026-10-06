import os
import pytest
from cffi import FFI
from cffi.ffiplatform import maybe_relative_path, flatten


def test_not_absolute():
    assert maybe_relative_path('foo/bar') == 'foo/bar'
    assert maybe_relative_path('test_platform.py') == 'test_platform.py'

def test_different_absolute():
    p = os.path.join('..', 'baz.py')
    assert maybe_relative_path(p) == p

def test_absolute_mapping():
    p = os.path.abspath('baz.py')
    assert maybe_relative_path(p) == 'baz.py'
    foobaz = os.path.join('foo', 'baz.py')
    assert maybe_relative_path(os.path.abspath(foobaz)) == foobaz

def test_flatten():
    assert flatten("foo") == "3sfoo"
    assert flatten(-10000000000000000000000000000) == \
           "-10000000000000000000000000000i"
    assert flatten([4, 5]) == "2l4i5i"
    assert flatten({4: 5}) == "1d4i5i"
    assert flatten({"foo": ("bar", "baaz")}) == "1d3sfoo2l3sbar4sbaaz"

@pytest.mark.thread_unsafe(reason="monkeypatches a shared distutils class method")
def test_compile_with_extra_build_ext_outputs(monkeypatch):
    # Some setuptools/distutils versions can make build_ext.get_outputs()
    # return more than one entry.
    from cffi._shimmed_dist_utils import build_ext as real_build_ext

    original_get_outputs = real_build_ext.get_outputs

    def get_outputs_with_extra_entry(self):
        return list(original_get_outputs(self)) + ['/nonexistent/other.so']

    monkeypatch.setattr(real_build_ext, 'get_outputs',
                        get_outputs_with_extra_entry)

    # force a fresh module name/compile every run, so the monkeypatched
    # get_outputs() above is actually exercised instead of reusing a
    # previously-built module cached under the same checksum-derived name
    tag = os.urandom(8).hex()

    ffi = FFI()
    ffi.cdef("double test_platform_extra_outputs(double x);")
    csrc = "double test_platform_extra_outputs(double x) { return x + 1.0; }"
    lib = ffi.verify(csrc, tag=tag)
    assert lib.test_platform_extra_outputs(41.0) == 42.0
