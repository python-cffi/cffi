import argparse
import pathlib

from cffi.api import FFI
from cffi.recompiler import Recompiler, NativeIO

parser = argparse.ArgumentParser(
    description="Generate source for a C module from the cffi build script."
)
parser.add_argument("--ffi_var_name", default="ffibuilder")
parser.add_argument("infile", type=pathlib.Path)
parser.add_argument("outfile", type=pathlib.Path)


class BuildError(Exception):
    __module__ = "cffi"


def execfile(filename, glob):
    # We use execfile() (here rewritten for Python 3) instead of
    # __import__() to load the build script.  The problem with
    # a normal import is that in some packages, the intermediate
    # __init__.py files may already try to import the file that
    # we are generating.
    with open(filename) as f:
        src = f.read()
    src += "\n"  # Python 2.6 compatibility
    code = compile(src, filename, "exec")
    exec(code, glob, glob)


def get_ffi(filename, ffi_var_name):
    globs = {}
    execfile(filename, globs)
    if ffi_var_name not in globs:
        raise BuildError("%r: object %r not found in module" % (filename, ffi_var_name))
    ffi = globs[ffi_var_name]
    if not isinstance(ffi, FFI) and callable(ffi):
        # Maybe it's a callable that returns a FFI
        ffi = ffi()
    if not isinstance(ffi, FFI):
        raise TypeError(
            "%r is not an FFI instance (got %r)" % (filename, type(ffi).__name__)
        )
    return ffi


def generate_c_source(ffi):
    """Generate C module source from a FFI instance.

      Example of use:
        if __name__ == "__main__":
          from cffi.buildtool import generate_c_source
          print(generate_c_source(ffibuilder))
    """
    # TODO: improve this; https://github.com/python-cffi/cffi/issues/47
    module_name, source, source_extension, kwds = ffi._assigned_source
    recompiler = Recompiler(ffi, module_name)
    recompiler.collect_type_table()
    recompiler.collect_step_tables()
    f = NativeIO()
    recompiler.write_source_to_f(f, source)
    return f.getvalue()


def main():
    args = parser.parse_args()
    ffi = get_ffi(args.infile, args.ffi_var_name)
    output = generate_c_source(ffi)
    with args.outfile.open("w") as f:
        f.write(output)
