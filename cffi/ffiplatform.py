import os


class VerificationError(Exception):
    """ An error raised when verification fails
    """

class VerificationMissing(Exception):
    """ An error raised when incomplete structures are passed into
    cdef, but no verification has been done
    """

test_file_counter = 0

def _get_test_file_base():
    # for now, living in the __pycache__ subdirectory
    global test_file_counter
    try:
        os.mkdir('__pycache__')
    except OSError:
        pass
    tst_file_base = '__pycache__/test%d' % test_file_counter
    test_file_counter += 1
    return tst_file_base
