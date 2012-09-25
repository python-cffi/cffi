
from cffi import FFI

ffi = FFI()
ffi.cdef("""     // some declarations from the man page
    struct passwd {
        char *pw_name;
        ...;
    };
    struct passwd *getpwuid(int uid);
""")
C = ffi.verify("""   // passed to the real C compiler
#include <sys/types.h>
#include <pwd.h>
""", libraries=[], ext_package="ext_package")
