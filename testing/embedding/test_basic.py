import py
import sys, os
import shutil, subprocess
from testing.udir import udir

local_dir = os.path.dirname(os.path.abspath(__file__))


class EmbeddingTests:
    _compiled_modules = set()

    def get_path(self):
        return str(udir.ensure('embedding', dir=True))

    def _run(self, args, env=None):
        print(args)
        popen = subprocess.Popen(args, env=env, cwd=self.get_path())
        err = popen.wait()
        if err:
            raise OSError("popen failed with exit code %r: %r" % (
                err, args))

    def prepare_module(self, name):
        if name not in self._compiled_modules:
            path = self.get_path()
            filename = '%s.py' % name
            # NOTE: if you have an .egg globally installed with an older
            # version of cffi, this will not work, because sys.path ends
            # up with the .egg before the PYTHONPATH entries.  I didn't
            # find a solution to that: we can hack sys.path inside the
            # script run here, but we can't hack it in the same way in
            # execute().
            env = os.environ.copy()
            env['PYTHONPATH'] = os.path.dirname(os.path.dirname(local_dir))
            self._run([sys.executable, os.path.join(local_dir, filename)],
                      env=env)
            self._compiled_modules.add(name)

    def compile(self, name, modules, **flags):
        path = self.get_path()
        filename = '%s.c' % name
        shutil.copy(os.path.join(local_dir, filename), path)
        if sys.platform.startswith('linux'):
            self._compile_linux(name, modules, **flags)
        elif sys.platform.startswith('win'):
            self._compile_win(name, modules, **flags)
        else:
            py.test.skip("don't know how to invoke the C compiler on %r" %
                         (sys.platform,))

    def _compile_linux(self, name, modules,
                       opt=False, threads=False, defines={}):
        path = self.get_path()
        filename = '%s.c' % name
        if 'CC' in os.environ:
            args = os.environ['CC'].split()
        else:
            args = ['gcc']
        if 'CFLAGS' in os.environ:
            args.extend(os.environ['CFLAGS'].split())
        if 'LDFLAGS' in os.environ:
            args.extend(os.environ['LDFLAGS'].split())
        if threads:
            args.append('-pthread')
        if opt:
            args.append('-O2')
        args.extend(['-g', filename, '-o', name, '-L.'])
        if '__pypy__' in sys.builtin_module_names:
            # xxx a bit hackish, maybe ffi.compile() should do a better job
            executable = os.path.abspath(sys.executable)
            libpypy_c = os.path.join(os.path.dirname(executable),
                                     'libpypy-c.so')
            try:
                os.symlink(libpypy_c, os.path.join(path, 'libpypy-c.so'))
            except OSError:
                pass
            args.extend(['%s.pypy-26.so' % modname for modname in modules])
            args.append('-lpypy-c')
        else:
            args.extend(['%s.so' % modname for modname in modules])
            args.append('-lpython2.7')
        args.append('-Wl,-rpath=$ORIGIN/')
        for key, value in sorted(defines.items()):
            args.append('-D%s=%s' % (key, value))
        self._run(args)

    def _compile_win(self, name, modules,
                     opt=False, threads=False, defines={}):
        xxxx

    def execute(self, name):
        path = self.get_path()
        env = os.environ.copy()
        env['PYTHONPATH'] = os.path.dirname(os.path.dirname(local_dir))
        print 'running %r in %r' % (name, path)
        popen = subprocess.Popen([name], cwd=path, env=env,
                                 stdout=subprocess.PIPE)
        result = popen.stdout.read()
        err = popen.wait()
        if err:
            raise OSError("%r failed with exit code %r" % (name, err))
        return result


class TestBasic(EmbeddingTests):
    def test_basic(self):
        self.prepare_module('add1')
        self.compile('add1-test', ['_add1_cffi'])
        output = self.execute('add1-test')
        assert output == ("preparing...\n"
                          "adding 40 and 2\n"
                          "adding 100 and -5\n"
                          "got: 42 95\n")

    def test_two_modules(self):
        self.prepare_module('add1')
        self.prepare_module('add2')
        self.compile('add2-test', ['_add1_cffi', '_add2_cffi'])
        output = self.execute('add2-test')
        assert output == ("preparing...\n"
                          "adding 40 and 2\n"
                          "prepADD2\n"
                          "adding 100 and -5 and -20\n"
                          "got: 42 75\n")
