project(
    'squared',
    'c',
    version: '0.1.0',
    default_options: ['warning_level=2'],
)

py = import('python').find_installation(pure: false)

install_subdir('src/squared', install_dir: py.get_install_dir())

gen_cffi_src = find_program('gen-cffi-src')

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
        gen_cffi_src,
        'read-sources',
        'squared._squared',
        '@INPUT0@',
        '@INPUT1@',
        '@OUTPUT@',
    ],
    output: '_squared.c',
    input: ['src/squared/squared.cdef.txt', 'src/squared/squared.csrc.c'],
)

py.extension_module(
    '_squared',
    squared_ext_src,
    subdir: 'squared',
    install: true,
    dependencies: [square_dep, py.dependency()],
)
