
from platformer import udir

class VerificationError(Exception):
    """ An error raised when verification fails
    """

class VerificationMissing(Exception):
    """ An error raised when incomplete structures are passed into
    cdef, but no verification has been done
    """

def _get_test_file():
    tst_file = udir.join('test.c')
    i = 0
    # XXX we want to put typedefs here
    while tst_file.check():
        tst_file = udir.join('test%d.c' % i)
        i += 1
    return tst_file
