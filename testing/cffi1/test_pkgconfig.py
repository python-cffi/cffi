import sys
import subprocess
import py
from cffi.pkgconfig import pkgconfig_installed, merge_dicts, pkgconfig_kwargs

def test_merge_dicts ():

    d1 = {"ham": [1, 2, 3], "spam" : ["a", "b", "c"], "foo" : []}
    d2 = {"spam" : ["spam", "spam", "spam"], "bar" : ["b", "a", "z"]}

    merge_dicts (d1, d2)
    assert d1 == {
        "ham": [1, 2, 3],
        "spam" : ["a", "b", "c", "spam", "spam", "spam"],
        "bar" : ["b", "a", "z"],
        "foo" : []}

def test_pkgconfig ():
    if not pkgconfig_installed:
        py.test.skip ("pkg-config is not installed on the system")

    version = sys.version_info.major
    kwargs = {}
    try:
        kwargs = pkgconfig_kwargs ("python%s" % version)
    except subprocess.CalledProcessError as e:
        py.test.skip ("No python%s pkg-config file installed" % version)
    
    assert any ("python" in lib for lib in kwargs ["libraries"]) == True
    assert any ("python" in dir for dir in kwargs ["include_dirs"]) == True
