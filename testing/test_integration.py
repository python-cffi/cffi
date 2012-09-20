
import py, sys, os
import tempfile

class DummyLogger(object):
    indent = 0
    
    def __getattr__(self, attr):
        return lambda *args: None

def create_venv():
    import virtualenv
    tmpdir = tempfile.mkdtemp()
    virtualenv.logger = DummyLogger()
    virtualenv.create_environment(tmpdir, site_packages=False)
    tmpdir = py.path.local(tmpdir)
    execfile(str(tmpdir.join("bin", "activate_this.py")))

SNIPPET_DIR = py.path.local(__file__).join('..', 'snippets')

def test_infrastructure():
    create_venv()
    oldargv = sys.argv
    olddir = os.getcwd()
    try:
        os.chdir(str(SNIPPET_DIR.join('infrastructure')))
        sys.argv = ['setup.py', 'install']
        execfile(str(SNIPPET_DIR.join('infrastructure', 'setup.py')))
    finally:
        sys.argv = oldargv
        os.chdir(olddir)
    import snip_infrastructure
    assert snip_infrastructure.func() == 42
