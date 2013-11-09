import sys, os
import subprocess
import errno


sources = ['c/_cffi_backend.c']
libraries = ['ffi']
include_dirs = ['/usr/include/ffi',
                '/usr/include/libffi']    # may be changed by pkg-config
define_macros = []
library_dirs = []
extra_compile_args = []
extra_link_args = []


def _ask_pkg_config(resultlist, option, result_prefix='', sysroot=False):
    pkg_config = os.environ.get('PKG_CONFIG','pkg-config')
    try:
        p = subprocess.Popen([pkg_config, option, 'libffi'],
                             stdout=subprocess.PIPE)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise
    else:
        t = p.stdout.read().decode().strip()
        if p.wait() == 0:
            res = t.split()
            # '-I/usr/...' -> '/usr/...'
            for x in res:
                assert x.startswith(result_prefix)
            res = [x[len(result_prefix):] for x in res]
            #print 'PKG_CONFIG:', option, res
            #
            sysroot = sysroot and os.environ.get('PKG_CONFIG_SYSROOT_DIR', '')
            if sysroot:
                # old versions of pkg-config don't support this env var,
                # so here we emulate its effect if needed
                res = [path if path.startswith(sysroot)
                            else sysroot + path
                         for path in res]
            #
            resultlist[:] = res

def ask_supports_thread():
    import distutils.errors
    from distutils.ccompiler import new_compiler
    compiler = new_compiler(force=1)
    try:
        compiler.compile(['c/check__thread.c'])
    except distutils.errors.CompileError:
        print >> sys.stderr, "will not use '__thread' in the C code"
    else:
        define_macros.append(('USE__THREAD', None))

def use_pkg_config():
    _ask_pkg_config(include_dirs,       '--cflags-only-I', '-I', sysroot=True)
    _ask_pkg_config(extra_compile_args, '--cflags-only-other')
    _ask_pkg_config(library_dirs,       '--libs-only-L', '-L', sysroot=True)
    _ask_pkg_config(extra_link_args,    '--libs-only-other')
    _ask_pkg_config(libraries,          '--libs-only-l', '-l')


if sys.platform == 'win32':
    COMPILE_LIBFFI = 'c/libffi_msvc'    # from the CPython distribution
else:
    COMPILE_LIBFFI = None

if COMPILE_LIBFFI:
    assert os.path.isdir(COMPILE_LIBFFI), "directory not found!"
    include_dirs[:] = [COMPILE_LIBFFI]
    libraries[:] = []
    _filenames = [filename.lower() for filename in os.listdir(COMPILE_LIBFFI)]
    _filenames = [filename for filename in _filenames
                           if filename.endswith('.c')]
    if sys.maxsize > 2**32:
        # 64-bit: unlist win32.c, and add instead win64.obj.  If the obj
        # happens to get outdated at some point in the future, you need to
        # rebuild it manually from win64.asm.
        _filenames.remove('win32.c')
        extra_link_args.append(os.path.join(COMPILE_LIBFFI, 'win64.obj'))
    sources.extend(os.path.join(COMPILE_LIBFFI, filename)
                   for filename in _filenames)
else:
    use_pkg_config()
    ask_supports_thread()


if __name__ == '__main__':
  from setuptools import setup, Feature, Extension
  setup(
    name='cffi',
    description='Foreign Function Interface for Python calling C code.',
    long_description="""
CFFI
====

Foreign Function Interface for Python calling C code.
Please see the `Documentation <http://cffi.readthedocs.org/>`_.

Contact
-------

`Mailing list <https://groups.google.com/forum/#!forum/python-cffi>`_
    """,
    version='0.8',
    packages=['cffi'],
    zip_safe=False,

    url='http://cffi.readthedocs.org',
    author='Armin Rigo, Maciej Fijalkowski',
    author_email='python-cffi@googlegroups.com',

    license='MIT',

    features={
        'cextension': Feature(
            "fast c backend for cpython",
            standard='__pypy__' not in sys.modules,
            ext_modules=[
                Extension(name='_cffi_backend',
                          include_dirs=include_dirs,
                          sources=sources,
                          libraries=libraries,
                          define_macros=define_macros,
                          library_dirs=library_dirs,
                          extra_compile_args=extra_compile_args,
                          extra_link_args=extra_link_args,
                          ),
            ],
        ),
    },

    install_requires=[
        'pycparser',
    ]
  )
