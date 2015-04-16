__all__ = ['FFI', 'VerificationError', 'VerificationMissing', 'CDefError',
           'FFIError']

from .api import FFI, CDefError
from .ffiplatform import VerificationError, VerificationMissing

FFIError = FFI.error    # backward compatibility

__version__ = "1.0.0"
__version_info__ = (1, 0, 0)
