import sys, os, imp, math, random
import py
from cffi import FFI, FFIError
from cffi.verifier import Verifier, _locate_engine_class
from testing.udir import udir


class DistUtilsTest(object):

    def test_locate_engine_class(self):
        cls = _locate_engine_class(FFI(), self.generic)
        if self.generic:
            # asked for the generic engine, which must not generate a
            # CPython extension module
            assert not cls._gen_python_module
        else:
            # asked for the CPython engine: check that we got it, unless
            # we are running on top of PyPy, where the generic engine is
            # always better
            if '__pypy__' not in sys.builtin_module_names:
                assert cls._gen_python_module

    def test_write_source(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!*/\n#include <math.h>\n'
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        v.write_source()
        with open(v.sourcefilename, 'r') as f:
            data = f.read()
        assert csrc in data

    def test_write_source_explicit_filename(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!*/\n#include <math.h>\n'
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        v.sourcefilename = filename = str(udir.join('write_source.c'))
        v.write_source()
        assert filename == v.sourcefilename
        with open(filename, 'r') as f:
            data = f.read()
        assert csrc in data

    def test_write_source_to_file_obj(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!*/\n#include <math.h>\n'
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        try:
            from StringIO import StringIO
        except ImportError:
            from io import StringIO
        f = StringIO()
        v.write_source(file=f)
        assert csrc in f.getvalue()

    def test_compile_module(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!*/\n#include <math.h>\n'
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        v.compile_module()
        assert v.get_module_name().startswith('_cffi_')
        if v.generates_python_module():
            mod = imp.load_dynamic(v.get_module_name(), v.modulefilename)
            assert hasattr(mod, '_cffi_setup')

    def test_compile_module_explicit_filename(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!2*/\n#include <math.h>\n'
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        basename = self.__class__.__name__ + 'test_compile_module'
        v.modulefilename = filename = str(udir.join(basename + '.so'))
        v.compile_module()
        assert filename == v.modulefilename
        assert v.get_module_name() == basename
        if v.generates_python_module():
            mod = imp.load_dynamic(v.get_module_name(), v.modulefilename)
            assert hasattr(mod, '_cffi_setup')

    def test_name_from_checksum_of_cdef(self):
        names = []
        for csrc in ['double', 'double', 'float']:
            ffi = FFI()
            ffi.cdef("%s sin(double x);" % csrc)
            v = Verifier(ffi, "#include <math.h>",
                         force_generic_engine=self.generic)
            names.append(v.get_module_name())
        assert names[0] == names[1] != names[2]

    def test_name_from_checksum_of_csrc(self):
        names = []
        for csrc in ['123', '123', '1234']:
            ffi = FFI()
            ffi.cdef("double sin(double x);")
            v = Verifier(ffi, csrc, force_generic_engine=self.generic)
            names.append(v.get_module_name())
        assert names[0] == names[1] != names[2]

    def test_load_library(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!3*/\n#include <math.h>\n'
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        library = v.load_library()
        assert library.sin(12.3) == math.sin(12.3)

    def test_verifier_args(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!4*/#include "test_verifier_args.h"\n'
        udir.join('test_verifier_args.h').write('#include <math.h>\n')
        v = Verifier(ffi, csrc, include_dirs=[str(udir)],
                     force_generic_engine=self.generic)
        library = v.load_library()
        assert library.sin(12.3) == math.sin(12.3)

    def test_verifier_object_from_ffi(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = "/*6*/\n#include <math.h>"
        lib = ffi.verify(csrc, force_generic_engine=self.generic)
        assert lib.sin(12.3) == math.sin(12.3)
        assert isinstance(ffi.verifier, Verifier)
        with open(ffi.verifier.sourcefilename, 'r') as f:
            data = f.read()
        assert csrc in data

    def test_extension_object(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '''/*7*/
    #include <math.h>
    #ifndef TEST_EXTENSION_OBJECT
    # error "define_macros missing"
    #endif
    '''
        lib = ffi.verify(csrc, define_macros=[('TEST_EXTENSION_OBJECT', '1')],
                         force_generic_engine=self.generic)
        assert lib.sin(12.3) == math.sin(12.3)
        v = ffi.verifier
        ext = v.get_extension()
        assert 'distutils.extension.Extension' in str(ext.__class__)
        assert ext.sources == [v.sourcefilename]
        assert ext.name == v.get_module_name()
        assert ext.define_macros == [('TEST_EXTENSION_OBJECT', '1')]

    def test_extension_forces_write_source(self):
        ffi = FFI()
        ffi.cdef("double sin(double x);")
        csrc = '/*hi there!%r*/\n#include <math.h>\n' % random.random()
        v = Verifier(ffi, csrc, force_generic_engine=self.generic)
        assert not os.path.exists(v.sourcefilename)
        v.get_extension()
        assert os.path.exists(v.sourcefilename)


class TestDistUtilsCPython(DistUtilsTest):
    generic = False

class TestDistUtilsGeneric(DistUtilsTest):
    generic = True
