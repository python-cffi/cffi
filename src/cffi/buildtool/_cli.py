# Integrated from the cffi-buildtool project by Rose Davidson
# (https://github.com/inklesspen/cffi-buildtool), MIT-licensed.
"""Command-line entry point for ``gen-cffi-src``.

Two subcommands:

``exec-python``
    Execute a Python build script that constructs a :class:`cffi.FFI`
    (the same kind of script that the CFFI docs' "Main mode of usage"
    describes) and emit the generated C source.

``read-sources``
    Build the :class:`cffi.FFI` from a separate ``cdef`` file and C
    source prelude, then emit the generated C source.
"""

import argparse

from ._gen import (
    find_ffi_in_python_script,
    generate_c_source,
    make_ffi_from_sources,
)


def exec_python(*, output, pyfile, ffi_var):
    with pyfile:
        ffi = find_ffi_in_python_script(pyfile.read(), pyfile.name, ffi_var)
    generated = generate_c_source(ffi)
    with output:
        output.write(generated)


def read_sources(*, output, module_name, cdef_input, csrc_input):
    with csrc_input, cdef_input:
        csrc = csrc_input.read()
        cdef = cdef_input.read()
    ffi = make_ffi_from_sources(module_name, cdef, csrc)
    generated = generate_c_source(ffi)
    with output:
        output.write(generated)


parser = argparse.ArgumentParser(
    prog='gen-cffi-src',
    description='Generate CFFI C source for a build backend (e.g. meson-python).',
)
subparsers = parser.add_subparsers(dest='mode')

exec_python_parser = subparsers.add_parser(
    'exec-python',
    help='Execute a Python script to build an FFI object',
)
exec_python_parser.add_argument(
    '--ffi-var',
    default='ffibuilder',
    help="Name of the FFI object in the Python script; defaults to 'ffibuilder'.",
)
exec_python_parser.add_argument(
    'pyfile',
    type=argparse.FileType('r', encoding='utf-8'),
    help='Path to the Python script',
)
exec_python_parser.add_argument(
    'output',
    type=argparse.FileType('w', encoding='utf-8'),
    help='Output path for the C source',
)

read_sources_parser = subparsers.add_parser(
    'read-sources',
    help='Read cdef and C source prelude files to build an FFI object',
)
read_sources_parser.add_argument(
    'module_name',
    help='Full name of the generated module, including packages',
)
read_sources_parser.add_argument(
    'cdef',
    type=argparse.FileType('r', encoding='utf-8'),
    help='File containing C definitions',
)
read_sources_parser.add_argument(
    'csrc',
    type=argparse.FileType('r', encoding='utf-8'),
    help='File containing C source prelude',
)
read_sources_parser.add_argument(
    'output',
    type=argparse.FileType('w', encoding='utf-8'),
    help='Output path for the C source',
)


def run(args=None):
    args = parser.parse_args(args=args)
    if args.mode == 'exec-python':
        exec_python(output=args.output, pyfile=args.pyfile, ffi_var=args.ffi_var)
    elif args.mode == 'read-sources':
        if args.cdef is args.csrc:
            parser.error('cdef and csrc are the same file and should not be')
        read_sources(
            output=args.output,
            module_name=args.module_name,
            cdef_input=args.cdef,
            csrc_input=args.csrc,
        )
    else:
        parser.error('a subcommand is required: exec-python or read-sources')
    parser.exit(0)
