"""Tests for the buildtool command-line tool.

The command line is the buildtool's only public interface, so these
tests drive it exclusively through subprocesses.
"""

import os
import shutil
import subprocess
import sys
import sysconfig

import pytest

pytestmark = [
    pytest.mark.thread_unsafe(reason="spawns subprocesses, slow"),
]


SIMPLE_SCRIPT = """\
from cffi import FFI

ffibuilder = FFI()

ffibuilder.cdef("int square(int n);")

ffibuilder.set_source("squared._squared", '#include "square.h"')

something_else = 42

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
"""

CALLABLE_SCRIPT = """\
from cffi import FFI

def make_ffi():
    ffibuilder = FFI()
    ffibuilder.cdef("int square(int n);")
    ffibuilder.set_source("squared._squared", '#include "square.h"')
    return ffibuilder

def something_else():
    return 42
"""


def _gen_cffi_src_path():
    """Locate the installed ``gen-cffi-src`` script, or return None."""
    exe = "gen-cffi-src" + (".exe" if sys.platform == "win32" else "")
    candidate = os.path.join(sysconfig.get_path("scripts"), exe)
    if os.path.exists(candidate):
        return candidate
    return shutil.which("gen-cffi-src")


def _run(argv, *args):
    return subprocess.run(
        [*argv, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )


# `gen-cffi-src` can also be invoked via `python -m cffi.buildtool`.
# This fixture enables testing both invocations.
@pytest.fixture(params=["module", "script"])
def run_buildtool(request):
    """Run the buildtool CLI in a subprocess, via both invocations."""
    if request.param == "script":
        script = _gen_cffi_src_path()
        if script is None:
            pytest.skip("the gen-cffi-src script is not installed")
        argv = [script]
    else:
        argv = [sys.executable, "-m", "cffi.buildtool"]

    def run(*args):
        return _run(argv, *args)

    return run


def test_exec_python(tmp_path, run_buildtool):
    pyfile = tmp_path / "_squared_build.py"
    pyfile.write_text(SIMPLE_SCRIPT)
    output = tmp_path / "out.c"
    proc = run_buildtool("exec-python", str(pyfile), str(output))
    assert proc.returncode == 0, proc.stderr
    generated = output.read_text()
    assert "square" in generated
    # sanity check: the emitted C source is the thing meson-python will compile
    assert "PyInit" in generated or "_cffi_f_" in generated


def test_exec_python_ffi_var(tmp_path, run_buildtool):
    pyfile = tmp_path / "_squared_build.py"
    pyfile.write_text(CALLABLE_SCRIPT)
    output = tmp_path / "out.c"
    proc = run_buildtool(
        "exec-python", "--ffi-var", "make_ffi", str(pyfile), str(output)
    )
    assert proc.returncode == 0, proc.stderr
    assert "square" in output.read_text()


def test_exec_python_name_not_found(tmp_path, run_buildtool):
    pyfile = tmp_path / "_squared_build.py"
    pyfile.write_text(SIMPLE_SCRIPT)
    output = tmp_path / "out.c"
    proc = run_buildtool(
        "exec-python", "--ffi-var", "notfound", str(pyfile), str(output)
    )
    assert proc.returncode != 0
    assert "NameError" in proc.stderr
    assert "'notfound'" in proc.stderr


@pytest.mark.parametrize(
    "script", [SIMPLE_SCRIPT, CALLABLE_SCRIPT], ids=["simple", "callable"]
)
def test_exec_python_wrong_type(tmp_path, run_buildtool, script):
    pyfile = tmp_path / "_squared_build.py"
    pyfile.write_text(script)
    output = tmp_path / "out.c"
    proc = run_buildtool(
        "exec-python", "--ffi-var", "something_else", str(pyfile), str(output)
    )
    assert proc.returncode != 0
    assert "not an instance of cffi.api.FFI" in proc.stderr


def test_read_sources(tmp_path, run_buildtool):
    cdef = tmp_path / "squared.cdef.txt"
    cdef.write_text("int square(int n);\n")
    csrc = tmp_path / "squared.csrc.c"
    csrc.write_text('#include "square.h"\n')
    output = tmp_path / "out.c"
    proc = run_buildtool(
        "read-sources", "squared._squared", str(cdef), str(csrc), str(output)
    )
    assert proc.returncode == 0, proc.stderr
    generated = output.read_text()
    assert "square" in generated
    assert "PyInit" in generated or "_cffi_f_" in generated


def test_read_sources_same_input_fails(run_buildtool):
    proc = run_buildtool("read-sources", "_squared", "-", "-", "-")
    assert proc.returncode != 0
    assert "are the same file and should not be" in proc.stderr


def test_no_subcommand(run_buildtool):
    proc = run_buildtool()
    assert proc.returncode != 0
    assert "a subcommand is required" in proc.stderr


def test_module_help_names_module_invocation():
    proc = _run([sys.executable, "-m", "cffi.buildtool"], "--help")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("usage: python -m cffi.buildtool")


def test_script_help_names_script_invocation():
    script = _gen_cffi_src_path()
    if script is None:
        pytest.skip("the gen-cffi-src script is not installed")
    proc = _run([script], "--help")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("usage: gen-cffi-src")


def test_import_is_inert():
    # importing the entry-point module must not run the CLI
    proc = subprocess.run(
        [sys.executable, "-c", "import cffi.buildtool"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == ""
    assert proc.stderr == ""
