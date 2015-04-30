
def error(msg):
    from distutils.errors import DistutilsSetupError
    raise DistutilsSetupError(msg)


def add_cffi_module(dist, mod_spec):
    import os
    from cffi.api import FFI
    from _cffi1 import recompiler
    from distutils.core import Extension
    from distutils.command.build_ext import build_ext
    from distutils.dir_util import mkpath
    from distutils import log

    if not isinstance(mod_spec, str):
        error("argument to 'cffi_modules=...' must be a str or a list of str,"
              " not %r" % (type(mod_spec).__name__,))
    try:
        build_mod_name, ffi_var_name = mod_spec.split(':')
    except ValueError:
        error("%r must be of the form 'build_mod_name:ffi_variable'" %
              (mod_spec,))
    mod = __import__(build_mod_name, None, None, [ffi_var_name])
    try:
        ffi = getattr(mod, ffi_var_name)
    except AttributeError:
        error("%r: object %r not found in module" % (mod_spec,
                                                     ffi_var_name))
    if not isinstance(ffi, FFI):
        error("%r is not an FFI instance (got %r)" % (mod_spec,
                                                      type(ffi).__name__))
    if not hasattr(ffi, '_assigned_source'):
        error("%r: the set_source() method was not called" % (mod_spec,))
    module_name = ffi._recompiler_module_name
    source, kwds = ffi._assigned_source

    allsources = ['$PLACEHOLDER']
    allsources.extend(kwds.get('sources', []))
    ext = Extension(name=module_name, sources=allsources, **kwds)

    def make_mod(tmpdir):
        file_name = module_name + '.c'
        log.info("generating cffi module %r" % file_name)
        output = recompiler.make_c_source(ffi, module_name, source)
        mkpath(tmpdir)
        c_file = os.path.join(tmpdir, file_name)
        try:
            with open(c_file, 'r') as f1:
                if f1.read() != output:
                    raise IOError
        except IOError:
            with open(c_file, 'w') as f1:
                f1.write(output)
        else:
            log.info("already up-to-date")
        return c_file

    if dist.ext_modules is None:
        dist.ext_modules = []
    dist.ext_modules.append(ext)

    base_class = dist.cmdclass.get('build_ext', build_ext)
    class build_ext_make_mod(base_class):
        def run(self):
            if ext.sources[0] == '$PLACEHOLDER':
                ext.sources[0] = make_mod(self.build_temp)
            base_class.run(self)
    dist.cmdclass['build_ext'] = build_ext_make_mod


def cffi_modules(dist, attr, value):
    assert attr == 'cffi_modules'
    if isinstance(value, str):
        value = [value]

    for cffi_module in value:
        add_cffi_module(dist, cffi_module)
