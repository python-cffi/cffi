import sys, os, binascii, imp, shutil
from . import __version__
from . import ffiplatform


class Verifier(object):

    def __init__(self, ffi, preamble, force_generic_engine=False, **kwds):
        self.ffi = ffi
        self.preamble = preamble
        vengine_class = _locate_engine_class(ffi, force_generic_engine)
        self._vengine = vengine_class(self)
        self._vengine.patch_extension_kwds(kwds)
        self.kwds = kwds
        #
        key = '\x00'.join(['1', sys.version[:3], __version__, preamble] +
                          ffi._cdefsources).encode('utf-8')
        k1 = hex(binascii.crc32(key[0::2]) & 0xffffffff)
        k1 = k1.lstrip('0x').rstrip('L')
        k2 = hex(binascii.crc32(key[1::2]) & 0xffffffff)
        k2 = k2.lstrip('0').rstrip('L')
        modulename = '_cffi_%s%s%s' % (self._vengine._class_key, k1, k2)
        suffix = _get_so_suffix()
        self.sourcefilename = os.path.join(_TMPDIR, modulename + '.c')
        self.modulefilename = os.path.join(_TMPDIR, modulename + suffix)
        self._has_source = False
        self._has_module = False

    def write_source(self, file=None):
        """Write the C source code.  It is produced in 'self.sourcefilename',
        which can be tweaked beforehand."""
        if self._has_source and file is None:
            raise ffiplatform.VerificationError("source code already written")
        self._write_source(file)

    def compile_module(self):
        """Write the C source code (if not done already) and compile it.
        This produces a dynamic link library in 'self.modulefilename'."""
        if self._has_module:
            raise ffiplatform.VerificationError("module already compiled")
        if not self._has_source:
            self._write_source()
        self._compile_module()

    def load_library(self):
        """Get a C module from this Verifier instance.
        Returns an instance of a FFILibrary class that behaves like the
        objects returned by ffi.dlopen(), but that delegates all
        operations to the C module.  If necessary, the C code is written
        and compiled first.
        """
        if not self._has_module:
            self._locate_module()
            if not self._has_module:
                self.compile_module()
        return self._load_library()

    def get_module_name(self):
        basename = os.path.basename(self.modulefilename)
        # kill both the .so extension and the other .'s, as introduced
        # by Python 3: 'basename.cpython-33m.so'
        return basename.split('.', 1)[0]

    def get_extension(self):
        if not self._has_source:
            self._write_source()
        sourcename = self.sourcefilename
        modname = self.get_module_name()
        return ffiplatform.get_extension(sourcename, modname, **self.kwds)

    def generates_python_module(self):
        return self._vengine._gen_python_module

    # ----------

    def _locate_module(self):
        if not os.path.isfile(self.modulefilename):
            try:
                f, filename, descr = imp.find_module(self.get_module_name())
            except ImportError:
                return
            if f is not None:
                f.close()
            self.modulefilename = filename
        self._vengine.collect_types()
        self._has_module = True

    def _write_source(self, file=None):
        must_close = (file is None)
        if must_close:
            _ensure_dir(self.sourcefilename)
            file = open(self.sourcefilename, 'w')
        self._vengine._f = file
        try:
            self._vengine.write_source_to_f()
        finally:
            del self._vengine._f
            if must_close:
                file.close()
        if file is None:
            self._has_source = True

    def _compile_module(self):
        # compile this C source
        tmpdir = os.path.dirname(self.sourcefilename)
        outputfilename = ffiplatform.compile(tmpdir, self.get_extension())
        try:
            same = ffiplatform.samefile(outputfilename, self.modulefilename)
        except OSError:
            same = False
        if not same:
            _ensure_dir(self.modulefilename)
            shutil.move(outputfilename, self.modulefilename)
        self._has_module = True

    def _load_library(self):
        assert self._has_module
        return self._vengine.load_library()

# ____________________________________________________________

_FORCE_GENERIC_ENGINE = False      # for tests

def _locate_engine_class(ffi, force_generic_engine):
    if _FORCE_GENERIC_ENGINE:
        force_generic_engine = True
    if not force_generic_engine:
        if '__pypy__' in sys.builtin_module_names:
            force_generic_engine = True
        else:
            try:
                import _cffi_backend
            except ImportError:
                _cffi_backend = '?'
            if ffi._backend is not _cffi_backend:
                force_generic_engine = True
    if force_generic_engine:
        from . import vengine_gen
        return vengine_gen.VGenericEngine
    else:
        from . import vengine_cpy
        return vengine_cpy.VCPythonEngine

# ____________________________________________________________

_TMPDIR = '__pycache__'

def set_tmpdir(dirname):
    """Set the temporary directory to use instead of __pycache__."""
    global _TMPDIR
    _TMPDIR = dirname

def cleanup_tmpdir(keep_so=False):
    """Clean up the temporary directory by removing all files in it
    called `_cffi_*.{c,so}` as well as the `build` subdirectory."""
    try:
        filelist = os.listdir(_TMPDIR)
    except OSError:
        return
    if keep_so:
        suffix = '.c'   # only remove .c files
    else:
        suffix = _get_so_suffix().lower()
    for fn in filelist:
        if fn.lower().startswith('_cffi_') and (
                fn.lower().endswith(suffix) or fn.lower().endswith('.c')):
            try:
                os.unlink(os.path.join(_TMPDIR, fn))
            except OSError:
                pass
    clean_dir = [os.path.join(_TMPDIR, 'build')]
    for dir in clean_dir:
        try:
            for fn in os.listdir(dir):
                fn = os.path.join(dir, fn)
                if os.path.isdir(fn):
                    clean_dir.append(fn)
                else:
                    os.unlink(fn)
        except OSError:
            pass

def _get_so_suffix():
    for suffix, mode, type in imp.get_suffixes():
        if type == imp.C_EXTENSION:
            return suffix
    raise ffiplatform.VerificationError("no C_EXTENSION available")

def _ensure_dir(filename):
    try:
        os.makedirs(os.path.dirname(filename))
    except OSError:
        pass
