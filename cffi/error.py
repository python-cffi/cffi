
class FFIError(Exception):
    pass

class CDefError(Exception):
    def __str__(self):
        try:
            current_decl = self.args[1]
            filename = current_decl.coord.file
            linenum = current_decl.coord.line
            prefix = '%s:%d: ' % (filename, linenum)
        except (AttributeError, TypeError, IndexError):
            prefix = ''
        return '%s%s' % (prefix, self.args[0])

class VerificationError(Exception):
    """ An error raised when verification fails
    """

class VerificationMissing(Exception):
    """ An error raised when incomplete structures are passed into
    cdef, but no verification has been done
    """

class PkgConfigNotFound(Exception):
    """ An error raised when pkgconfig was not found"""

class PkgConfigError(Exception):
    """ Generic super class for pkg-config related errors"""

class PkgConfigModuleNotFound(PkgConfigError):
    """ Module or it's pkg-config file was not found on a system"""

class PkgConfigModuleVersionNotFound(PkgConfigError):
    """ Requested version of module was not found"""
