# pkg-config, https://www.freedesktop.org/wiki/Software/pkg-config/ integration for cffi
import subprocess

def pkgconfig_installed ():
    """Check if pkg=config is installed or not"""
    try:
        subprocess.check_output (["pkg-config", "--version"])
        return True
    except subprocess.CalledProcessError:
        return False

def merge_dicts (d1, d2):
    """Helper function to merge two dicts with lists"""
    for key, value in d2.items ():
        if not key in d1:
            d1 [key] = value
        else:
            d1 [key].extend (value)
    return d1

def pkgconfig_kwargs (libs):
    r"""Return kwargs for FFI.set_source based on pkg-config output

    Usage
        ...
        ffibuilder.set_source ("_foo", libraries = ["foo", "bar"], pkgconfig = ["libfoo", "libbar"])

    If pkg-config is installed on build machine, then arguments include_dirs,
    library_dirs and define_macros are extended with an output of pkg-config
    [command] libfoo and pkgconfig [command] libbar. Argument libraries is
    replaced by an output of pkgconfig --libs-only-l calls.
    """

    # make API great again!
    if isinstance (libs, (str, bytes)):
        libs = (libs, )
    
    # drop starting -I -L -l from cflags
    def dropILl (string):
        def _dropILl (string):
            if string.startswith ("-I") or string.startswith ("-L") or string.startswith ("-l"):
                return string [2:]
        return [_dropILl (x) for x in string.split ()]

    # convert -Dfoo=bar to list of tuples [("foo", "bar")] expected by cffi
    def macros (string):
        def _macros (string):
            return tuple (string [2:].split ('=', 2))
        return [_macros (x) for x in string.split () if x.startswith ("-D")]

    def drop_macros (string):
        return [x for x in string.split () if not x.startswith ("-D")]

    # pkg-config call
    def pc (libname, *args):
        a = ["pkg-config", "--print-errors"]
        a.extend (args)
        a.append (libname)
        return subprocess.check_output (a)

    # return kwargs for given libname
    def kwargs (libname):
        return {
                "include_dirs" : dropILl (pc (libname, "--cflags-only-I")),
                "library_dirs" : dropILl (pc (libname, "--libs-only-L")),
                "libraries" : dropILl (pc (libname, "--libs-only-l")),
                "define_macros" : macros (pc (libname, "--cflags-only-other")),
                "extra_compile_args" : drop_macros (pc (libname, "--cflags-only-other")),
                "extra_link_args" : pc (libname, "--libs-only-other").split ()
                }

    # merge all arguments together
    ret = {}
    for libname in libs:
        foo = kwargs (libname)
        merge_dicts (ret, foo)

    return ret

