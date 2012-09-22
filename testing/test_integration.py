
import py, os, sys
import tempfile
import subprocess

class DummyLogger(object):
    indent = 0
    
    def __getattr__(self, attr):
        return lambda *args: None

def create_venv():
    import virtualenv
    tmpdir = tempfile.mkdtemp()
    virtualenv.logger = DummyLogger()
    virtualenv.create_environment(tmpdir, site_packages=False)
    return py.path.local(tmpdir)

SNIPPET_DIR = py.path.local(__file__).join('..', 'snippets')

def run_setup_and_program(dirname, venv_dir, python_snippet):
    olddir = os.getcwd()
    tmpdir2 = py.path.local(tempfile.mkdtemp()) # this is for python files
    python_f = tmpdir2.join('x.py')
    python_f.write(py.code.Source(python_snippet))
    try:
        os.chdir(str(SNIPPET_DIR.join(dirname)))
        python = sys.executable
        venv = venv_dir.join('bin/activate')
        p = subprocess.Popen(['bash', '-c', '. %(venv)s && %(python)s setup.py '
                              'install && %(python)s %(python_f)s' % locals()],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            print stdout
            print stderr
            raise Exception("crashed")
    finally:
        os.chdir(olddir)

def test_infrastructure():
    venv_dir = create_venv()
    run_setup_and_program('infrastructure', venv_dir, '''
    import snip_infrastructure
    assert snip_infrastructure.func() == 42
    ''')

def test_basic_verify():
    venv_dir = create_venv()
    run_setup_and_program("basic_verify", venv_dir, '''
    import snip_basic_verify
    p = snip_basic_verify.C.getpwuid(0)
    assert snip_basic_verify.ffi.string(p.pw_name) == "root"
    ''')
