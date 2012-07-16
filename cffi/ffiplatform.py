import os


class VerificationError(Exception):
    """ An error raised when verification fails
    """

class VerificationMissing(Exception):
    """ An error raised when incomplete structures are passed into
    cdef, but no verification has been done
    """


def get_extension(srcfilename, modname, **kwds):
    from distutils.core import Extension
    return Extension(name=modname, sources=[srcfilename], **kwds)

def compile(tmpdir, ext):
    """Compile a C extension module using distutils."""

    saved_environ = os.environ.copy()
    saved_path = os.getcwd()
    try:
        os.chdir(tmpdir)
        outputfilename = _build(ext)
        outputfilename = os.path.abspath(outputfilename)
    finally:
        os.chdir(saved_path)
        # workaround for a distutils bugs where some env vars can
        # become longer and longer every time it is used
        for key, value in saved_environ.items():
            if os.environ.get(key) != value:
                os.environ[key] = value
    return outputfilename

def _build(ext):
    # XXX compact but horrible :-(
    from distutils.core import Distribution
    import distutils.errors
    #
    dist = Distribution({'ext_modules': [ext]})
    options = dist.get_option_dict('build_ext')
    options['force'] = ('ffiplatform', True)
    #
    try:
        dist.run_command('build_ext')
    except (distutils.errors.CompileError,
            distutils.errors.LinkError), e:
        raise VerificationError('%s: %s' % (e.__class__.__name__, e))
    #
    cmd_obj = dist.get_command_obj('build_ext')
    [soname] = cmd_obj.get_outputs()
    return soname
