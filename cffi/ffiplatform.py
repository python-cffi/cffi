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
