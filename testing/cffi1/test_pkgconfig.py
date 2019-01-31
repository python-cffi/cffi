import sys
import subprocess
import py
import cffi.pkgconfig as pkgconfig

def mock_call(libname, flag):
    assert libname=="python-3.6", "mocked pc function supports python-3.6 input ONLY"

    flags = {
        "--cflags-only-I": b"-I/usr/include/python3.6m\n",
        "--libs-only-L": b"-L/usr/lib64\n",
        "--libs-only-l": b"-lpython3.6\n",
        "--cflags-only-other": b"-DCFFI_TEST=1 -O42\n",
        "--libs-only-other": b"-lm\n",
    }
    return flags[flag]

pkgconfig.call = mock_call


def test_merge_flags():

    d1 = {"ham": [1, 2, 3], "spam" : ["a", "b", "c"], "foo" : []}
    d2 = {"spam" : ["spam", "spam", "spam"], "bar" : ["b", "a", "z"]}

    pkgconfig.merge_flags(d1, d2)
    assert d1 == {
        "ham": [1, 2, 3],
        "spam" : ["a", "b", "c", "spam", "spam", "spam"],
        "bar" : ["b", "a", "z"],
        "foo" : []}


def test_pkgconfig():
    flags = pkgconfig.flags("python-3.6")
    assert flags == {
        'include_dirs': [u'/usr/include/python3.6m'],
        'library_dirs': [u'/usr/lib64'],
        'libraries': [u'python3.6'],
        'define_macros': [(u'CFFI_TEST', u'1')],
        'extra_compile_args': [u'-O42'],
        'extra_link_args': [u'-lm']
    }
