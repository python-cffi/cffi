
import py, os, sys
import subprocess
from testing.udir import udir

class DummyLogger(object):
    indent = 0
    
    def __getattr__(self, attr):
        return lambda *args: None

def create_venv(name):
    tmpdir = udir.join(name)
    subprocess.call(['virtualenv', '-p', sys.executable, str(tmpdir)])
    return tmpdir

SNIPPET_DIR = py.path.local(__file__).join('..', 'snippets')

def run_setup_and_program(dirname, venv_dir, python_snippet):
    olddir = os.getcwd()
    python_f = udir.join('x.py')
    python_f.write(py.code.Source(python_snippet))
    try:
        os.chdir(str(SNIPPET_DIR.join(dirname)))
        venv = venv_dir.join('bin/activate')
        p = subprocess.Popen(['bash', '-c', '. %(venv)s && python setup.py '
                              'install && python %(python_f)s' % locals()],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = p.communicate()
        if p.returncode != 0:
            print stdout
            print stderr
            raise Exception("crashed")
    finally:
        os.chdir(olddir)

def test_infrastructure():
    venv_dir = create_venv('infrastructure')
    run_setup_and_program('infrastructure', venv_dir, '''
    import snip_infrastructure
    assert snip_infrastructure.func() == 42
    ''')

def test_basic_verify():
    venv_dir = create_venv('basic_verify')
    run_setup_and_program("basic_verify", venv_dir, '''
    import snip_basic_verify
    p = snip_basic_verify.C.getpwuid(0)
    assert snip_basic_verify.ffi.string(p.pw_name) == "root"
    ''')

def test_setuptools_verify():
    venv_dir = create_venv('setuptools_verify')
    run_setup_and_program("setuptools_verify", venv_dir, '''
    import snip_setuptools_verify
    p = snip_setuptools_verify.C.getpwuid(0)
    assert snip_setuptools_verify.ffi.string(p.pw_name) == "root"
    ''')
    
def test_package():
    venv_dir = create_venv('package')
    run_setup_and_program("package", venv_dir, '''
    import snip_package
    p = snip_package.C.getpwuid(0)
    assert snip_package.ffi.string(p.pw_name) == "root"
    ''')
