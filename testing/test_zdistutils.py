import os, imp, math, StringIO, random
import py
from cffi import FFI, FFIError
from cffi.verifier import Verifier
from testing.udir import udir


def test_write_source():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!*/\n#include <math.h>\n'
    v = Verifier(ffi, csrc)
    v.write_source()
    with file(v.sourcefilename, 'r') as f:
        data = f.read()
    assert csrc in data

def test_write_source_explicit_filename():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!*/\n#include <math.h>\n'
    v = Verifier(ffi, csrc)
    v.sourcefilename = filename = str(udir.join('write_source.c'))
    v.write_source()
    assert filename == v.sourcefilename
    with file(filename, 'r') as f:
        data = f.read()
    assert csrc in data

def test_write_source_to_file_obj():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!*/\n#include <math.h>\n'
    v = Verifier(ffi, csrc)
    f = StringIO.StringIO()
    v.write_source(file=f)
    assert csrc in f.getvalue()

def test_compile_module():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!*/\n#include <math.h>\n'
    v = Verifier(ffi, csrc)
    v.compile_module()
    assert v.get_module_name().startswith('_cffi_')
    mod = imp.load_dynamic(v.get_module_name(), v.modulefilename)
    assert hasattr(mod, '_cffi_setup')

def test_compile_module_explicit_filename():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!2*/\n#include <math.h>\n'
    v = Verifier(ffi, csrc)
    v.modulefilename = filename = str(udir.join('test_compile_module.so'))
    v.compile_module()
    assert filename == v.modulefilename
    assert v.get_module_name() == 'test_compile_module'
    mod = imp.load_dynamic(v.get_module_name(), v.modulefilename)
    assert hasattr(mod, '_cffi_setup')

def test_name_from_md5_of_cdef():
    names = []
    for csrc in ['double', 'double', 'float']:
        ffi = FFI()
        ffi.cdef("%s sin(double x);" % csrc)
        v = Verifier(ffi, "#include <math.h>")
        names.append(v.get_module_name())
    assert names[0] == names[1] != names[2]

def test_name_from_md5_of_csrc():
    names = []
    for csrc in ['123', '123', '1234']:
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        v = Verifier(ffi, csrc)
        names.append(v.get_module_name())
    assert names[0] == names[1] != names[2]

def test_load_library():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!3*/\n#include <math.h>\n'
    v = Verifier(ffi, csrc)
    library = v.load_library()
    assert library.sin(12.3) == math.sin(12.3)

def test_verifier_args():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!4*/#include "test_verifier_args.h"\n'
    udir.join('test_verifier_args.h').write('#include <math.h>\n')
    v = Verifier(ffi, csrc, include_dirs=[str(udir)])
    library = v.load_library()
    assert library.sin(12.3) == math.sin(12.3)

def test_verifier_object_from_ffi():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = "/*6*/\n#include <math.h>"
    lib = ffi.verify(csrc)
    assert lib.sin(12.3) == math.sin(12.3)
    assert isinstance(ffi.verifier, Verifier)
    with file(ffi.verifier.sourcefilename, 'r') as f:
        data = f.read()
    assert csrc in data

def test_extension_object():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '''/*7*/
#include <math.h>
#ifndef TEST_EXTENSION_OBJECT
# error "define_macros missing"
#endif
'''
    lib = ffi.verify(csrc, define_macros=[('TEST_EXTENSION_OBJECT', '1')])
    assert lib.sin(12.3) == math.sin(12.3)
    v = ffi.verifier
    ext = v.get_extension()
    assert str(ext.__class__) == 'distutils.extension.Extension'
    assert ext.sources == [v.sourcefilename]
    assert ext.name == v.get_module_name()
    assert ext.define_macros == [('TEST_EXTENSION_OBJECT', '1')]

def test_extension_forces_write_source():
    ffi = FFI()
    ffi.cdef("double sin(double x);")
    csrc = '/*hi there!%r*/\n#include <math.h>\n' % random.random()
    v = Verifier(ffi, csrc)
    assert not os.path.exists(v.sourcefilename)
    v.get_extension()
    assert os.path.exists(v.sourcefilename)
