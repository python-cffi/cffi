import os


class VerificationError(Exception):
    """ An error raised when verification fails
    """

class VerificationMissing(Exception):
    """ An error raised when incomplete structures are passed into
    cdef, but no verification has been done
    """

_file_counter = 0
_tmpdir = None

def undercffi_module_name():
    global _file_counter
    modname = '_cffi_%d' % _file_counter
    _file_counter += 1
    return modname

def tmpdir():
    # for now, living in the __pycache__ subdirectory
    global _tmpdir
    if _tmpdir is None:
        try:
            os.mkdir('__pycache__')
        except OSError:
            pass
        _tmpdir = os.path.abspath('__pycache__')
    return _tmpdir


def compile(tmpdir, modname, **kwds):
    """Compile a C extension module using distutils."""

    saved_environ = os.environ.copy()
    saved_path = os.getcwd()
    try:
        os.chdir(tmpdir)
        outputfilename = _build(modname, kwds)
        outputfilename = os.path.abspath(outputfilename)
    finally:
        os.chdir(saved_path)
        # workaround for a distutils bugs where some env vars can
        # become longer and longer every time it is used
        for key, value in saved_environ.items():
            if os.environ.get(key) != value:
                os.environ[key] = value
    return outputfilename

def _build(modname, kwds):
    # XXX compact but horrible :-(
    from distutils.core import Distribution, Extension
    import distutils.errors
    #
    ext = Extension(name=modname, sources=[modname + '.c'], **kwds)
    dist = Distribution({'ext_modules': [ext]})
    options = dist.get_option_dict('build_ext')
    options['force'] = ('ffiplatform', True)
    #
    try:
        dist.run_command('build_ext')
    except (distutils.errors.CompileError,
            distutils.errors.LinkError), e:
        raise VerificationError(str(e))
    #
    cmd_obj = dist.get_command_obj('build_ext')
    [soname] = cmd_obj.get_outputs()
    return soname
