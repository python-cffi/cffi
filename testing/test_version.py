import os
import cffi, _cffi_backend

def test_version():
    v = cffi.__version__
    version_info = '.'.join(str(i) for i in cffi.__version_info__)
    assert v == version_info
    assert v == _cffi_backend.__version__

def test_doc_version():
    parent = os.path.dirname(os.path.dirname(__file__))
    p = os.path.join(parent, 'doc', 'source', 'conf.py')
    content = open(p).read()
    #
    v = cffi.__version__
    assert ("version = '%s'\n" % v) in content
    assert ("release = '%s'\n" % v) in content
    #
    p = os.path.join(parent, 'doc', 'source', 'index.rst')
    content = open(p).read()
    assert ("release-%s.tar.bz2" % v) in content

def test_setup_version():
    parent = os.path.dirname(os.path.dirname(__file__))
    p = os.path.join(parent, 'setup.py')
    content = open(p).read()
    #
    v = cffi.__version__
    assert ("version='%s'" % v) in content
