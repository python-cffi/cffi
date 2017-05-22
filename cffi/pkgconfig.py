# pkg-config, https://www.freedesktop.org/wiki/Software/pkg-config/ integration for cffi
import subprocess

def pkgconfig_installed ():
    try:
        subprocess.check_output (["pkg-config", "--version"])
        return True
    except subprocess.CalledProcessError:
        return False

def merge_dicts (d1, d2):
    for key, value in d2.items ():
        if not key in d1:
            d1 [key] = value
        else:
            d1 [key].extend (value)
    return d1

def pkgconfig_kwargs (libs):
    """If pkg-config is available, then return kwargs for set_source based on pkg-config output
    
    It setup include_dirs, library_dirs, libraries and define_macros
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
                "define_macros" : macros (pc (libname, "--cflags")),
                }

    # merge all arguments together
    ret = {}
    for libname in libs:
        foo = kwargs (libname)
        merge_dicts (ret, foo)

    return ret

