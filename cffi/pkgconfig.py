# pkg-config, https://www.freedesktop.org/wiki/Software/pkg-config/ integration for cffi
import subprocess
import sys
import re

from .error import PkgConfigModuleVersionNotFound
from .error import PkgConfigError

def merge_flags(cfg1, cfg2):
    """Merge values from cffi config flags cfg2 to cf1

    Example:
        merge_flags({"libraries": ["one"]}, {"libraries": "two"})
        {"libraries}" : ["one", "two"]}
    """
    for key, value in cfg2.items():
        if not key in cfg1:
            cfg1 [key] = value
        else:
            cfg1 [key].extend(value)
    return cfg1


def call(libname, flag):
    """Calls pkg-config and returing the output if found
    """
    a = ["pkg-config", "--print-errors"]
    a.append(flag)
    a.append(libname)
    pc = None
    try:
        pc = subprocess.Popen(a, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        pass
    if pc is None:
        raise PkgConfigError("pkg-config was not found on this system")
    
    bout, berr = pc.communicate()
    if berr is not None:
        err = berr.decode(sys.getfilesystemencoding())
        if re.search("Requested '.*' but version of ", err, re.MULTILINE) is not None:
            raise PkgConfigModuleVersionNotFound(err)
        else:
            PkgConfigError(err)
    return bout


def flags(libs):
    r"""Return compiler line flags for FFI.set_source based on pkg-config output

    Usage
        ...
        ffibuilder.set_source("_foo", pkgconfig = ["libfoo", "libbar >= 1.8.3"])

    If pkg-config is installed on build machine, then arguments include_dirs,
    library_dirs, libraries, define_macros, extra_compile_args and
    extra_link_args are extended with an output of pkg-config for libfoo and
    libbar.

    Raises
    * PkgConfigModuleVersionNotFound if requested version does not match
    * PkgConfigError for all other errors
    """

    subprocess.check_output(["pkg-config", "--version"])

    # make API great again!
    if isinstance(libs, (str, bytes)):
        libs = (libs, )
    
    # drop starting -I -L -l from cflags
    def dropILl(string):
        def _dropILl(string):
            if string.startswith("-I") or string.startswith("-L") or string.startswith("-l"):
                return string [2:]
        return [_dropILl(x) for x in string.split()]

    # convert -Dfoo=bar to list of tuples [("foo", "bar")] expected by cffi
    def macros(string):
        def _macros(string):
            return tuple(string [2:].split("=", 2))
        return [_macros(x) for x in string.split() if x.startswith("-D")]

    def drop_macros(string):
        return [x for x in string.split() if not x.startswith("-D")]

    # return kwargs for given libname
    def kwargs(libname):
        fse = sys.getfilesystemencoding()
        return {
                "include_dirs" : dropILl(call(libname, "--cflags-only-I").decode(fse)),
                "library_dirs" : dropILl(call(libname, "--libs-only-L").decode(fse)),
                "libraries" : dropILl(call(libname, "--libs-only-l").decode(fse)),
                "define_macros" : macros(call(libname, "--cflags-only-other").decode('ascii')),
                "extra_compile_args" : drop_macros(call(libname, "--cflags-only-other").decode('ascii')),
                "extra_link_args" : call(libname, "--libs-only-other").decode('ascii').split()
                }

    # merge all arguments together
    ret = {}
    for libname in libs:
        foo = kwargs(libname)
        merge_flags(ret, foo)

    return ret
