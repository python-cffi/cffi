project(
    'squared',
    'c',
    version: '0.1.0',
    default_options: ['warning_level=2'],
)

py = import('python').find_installation(pure: false)

install_subdir('src/squared', install_dir: py.get_install_dir())

cffi_gen_src = find_program('cffi-gen-src')

square_lib = static_library(
    'square',
    'src/csrc/square.c',
    include_directories: include_directories('src/csrc'),
)
square_dep = declare_dependency(
    link_with: square_lib,
    include_directories: include_directories('src/csrc'),
)

squared_ext_src = custom_target(
    'squared-cffi-src',
    command: [
        cffi_gen_src,
        'exec-python',
        '@INPUT@',
        '@OUTPUT@',
    ],
    output: '_squared.c',
    input: ['src/squared/_squared_build.py'],
)

py.extension_module(
    '_squared',
    squared_ext_src,
    subdir: 'squared',
    install: true,
    dependencies: [square_dep],
    # _cffi_include.h defines Py_LIMITED_API by default under MSVC, and
    # pyconfig.h then asks the linker for python3.lib via a #pragma.  Only
    # meson's limited_api: kwarg puts that library on the link line, so build
    # an ordinary extension instead.
    c_args: ['-D_CFFI_NO_LIMITED_API'],
)
