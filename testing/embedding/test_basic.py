import py
import sys, os, re
import shutil, subprocess, time
from testing.udir import udir

local_dir = os.path.dirname(os.path.abspath(__file__))


class EmbeddingTests:
    _compiled_modules = {}

    def setup_method(self, meth):
        self._path = udir.join('embedding', meth.__name__)

    def get_path(self):
        return str(self._path.ensure(dir=1))

    def _run(self, args, env=None):
        print(args)
        popen = subprocess.Popen(args, env=env, cwd=self.get_path(), stdout=subprocess.PIPE)
        output = popen.stdout.read()
        err = popen.wait()
        if err:
            raise OSError("popen failed with exit code %r: %r" % (
                err, args))
        print(output.rstrip())
        return output

    def prepare_module(self, name):
        if name not in self._compiled_modules:
            path = self.get_path()
            filename = '%s.py' % name
            # NOTE: if you have an .egg globally installed with an older
            # version of cffi, this will not work, because sys.path ends
            # up with the .egg before the PYTHONPATH entries.  I didn't
            # find a solution to that: we could hack sys.path inside the
            # script run here, but we can't hack it in the same way in
            # execute().
            env = os.environ.copy()
            env['PYTHONPATH'] = os.path.dirname(os.path.dirname(local_dir))
            output = self._run([sys.executable, os.path.join(local_dir, filename)],
                               env=env)
            match = re.compile(r"\bFILENAME: (.+)").search(output)
            assert match
            dynamic_lib_name = match.group(1)
            self._compiled_modules[name] = dynamic_lib_name
        return self._compiled_modules[name]

    def compile(self, name, modules, opt=False, threads=False, defines={}):
        path = self.get_path()
        filename = '%s.c' % name
        shutil.copy(os.path.join(local_dir, filename), path)
        import distutils.ccompiler
        curdir = os.getcwd()
        try:
            os.chdir(self.get_path())
            c = distutils.ccompiler.new_compiler()
            print('compiling %s with %r' % (name, modules))
            extra_preargs = []
            if threads and sys.platform != 'win32':
                extra_preargs.append('-pthread')
            objects = c.compile([filename], macros=sorted(defines.items()), debug=True)
            c.link_executable(objects + modules, name, extra_preargs=extra_preargs)
        finally:
            os.chdir(curdir)

    def execute(self, name):
        path = self.get_path()
        env = os.environ.copy()
        env['PYTHONPATH'] = os.path.dirname(os.path.dirname(local_dir))
        env['LD_LIBRARY_PATH'] = path
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
        add1_cffi = self.prepare_module('add1')
        self.compile('add1-test', [add1_cffi])
        output = self.execute('add1-test')
        assert output == ("preparing...\n"
                          "adding 40 and 2\n"
                          "adding 100 and -5\n"
                          "got: 42 95\n")

    def test_two_modules(self):
        add1_cffi = self.prepare_module('add1')
        add2_cffi = self.prepare_module('add2')
        self.compile('add2-test', [add1_cffi, add2_cffi])
        output = self.execute('add2-test')
        assert output == ("preparing...\n"
                          "adding 40 and 2\n"
                          "prepADD2\n"
                          "adding 100 and -5 and -20\n"
                          "got: 42 75\n")
