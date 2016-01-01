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
            env = os.environ.copy()
            env['PYTHONPATH'] = os.path.dirname(os.path.dirname(local_dir))
            self._run([sys.executable, os.path.join(local_dir, filename)],
                      env=env)
            self._compiled_modules.add(name)

    def compile(self, name, modules):
        path = self.get_path()
        filename = '%s.c' % name
        shutil.copy(os.path.join(local_dir, filename), path)
        self._run(['gcc', filename, '-o', name, '-L.'] +
                  ['%s.so' % modname for modname in modules] +
                  ['-lpython2.7', '-Wl,-rpath=$ORIGIN/'])

    def execute(self, name):
        path = self.get_path()
        popen = subprocess.Popen([name], cwd=path, stdout=subprocess.PIPE)
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
        assert output == ("preparing\n"
                          "adding 40 and 2\n"
                          "adding 100 and -5\n"
                          "got: 42 95\n")

    def test_two_modules(self):
        self.prepare_module('add1')
        self.prepare_module('add2')
        self.compile('add2-test', ['_add1_cffi', '_add2_cffi'])
        output = self.execute('add2-test')
        assert output == ("preparing\n"
                          "adding 40 and 2\n"
                          "preparing ADD2\n"
                          "adding 100 and -5 and -20\n"
                          "got: 42 75\n")
