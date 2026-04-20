import pytest

from cffi.buildtool import (
    find_ffi_in_python_script,
    generate_c_source,
    make_ffi_from_sources,
)
from cffi.buildtool import _cli as buildtool_cli


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


def _dont_exit(_status):
    pass


def test_find_ffi_simple():
    ffi = find_ffi_in_python_script(SIMPLE_SCRIPT, "_squared_build.py", "ffibuilder")
    module_name, csrc, _source_extension, _kwds = ffi._assigned_source
    assert module_name == "squared._squared"
    assert csrc.strip() == '#include "square.h"'
    cdef = "\n".join(ffi._cdefsources)
    assert "int square" in cdef


def test_find_ffi_callable():
    ffi = find_ffi_in_python_script(CALLABLE_SCRIPT, "_squared_build.py", "make_ffi")
    module_name, csrc, _source_extension, _kwds = ffi._assigned_source
    assert module_name == "squared._squared"
    assert csrc.strip() == '#include "square.h"'
    cdef = "\n".join(ffi._cdefsources)
    assert "int square" in cdef


def test_find_ffi_name_not_found():
    with pytest.raises(NameError, match="'notfound'"):
        find_ffi_in_python_script(SIMPLE_SCRIPT, "_squared_build.py", "notfound")


def test_find_ffi_wrong_type():
    with pytest.raises(TypeError, match="not an instance of cffi.api.FFI"):
        find_ffi_in_python_script(SIMPLE_SCRIPT, "_squared_build.py", "something_else")


def test_find_ffi_callable_wrong_type():
    with pytest.raises(TypeError, match="not an instance of cffi.api.FFI"):
        find_ffi_in_python_script(CALLABLE_SCRIPT, "_squared_build.py", "something_else")


def test_make_ffi_from_sources_and_generate():
    ffi = make_ffi_from_sources(
        "squared._squared",
        "int square(int n);",
        '#include "square.h"',
    )
    c_source = generate_c_source(ffi)
    assert "square" in c_source
    # sanity check: the emitted C source is the thing meson-python will compile
    assert "PyInit" in c_source or "_cffi_f_" in c_source


def test_cli_exec_python(tmp_path, monkeypatch):
    monkeypatch.setattr(buildtool_cli.parser, "exit", _dont_exit)
    pyfile = tmp_path / "_squared_build.py"
    pyfile.write_text(SIMPLE_SCRIPT)
    output = tmp_path / "out.c"
    buildtool_cli.run(["exec-python", str(pyfile), str(output)])
    generated = output.read_text()
    assert "square" in generated


def test_cli_exec_python_ffi_var(tmp_path, monkeypatch):
    monkeypatch.setattr(buildtool_cli.parser, "exit", _dont_exit)
    pyfile = tmp_path / "_squared_build.py"
    pyfile.write_text(CALLABLE_SCRIPT)
    output = tmp_path / "out.c"
    buildtool_cli.run(["exec-python", "--ffi-var", "make_ffi", str(pyfile), str(output)])
    generated = output.read_text()
    assert "square" in generated


def test_cli_read_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(buildtool_cli.parser, "exit", _dont_exit)
    cdef = tmp_path / "squared.cdef.txt"
    cdef.write_text("int square(int n);\n")
    csrc = tmp_path / "squared.csrc.c"
    csrc.write_text('#include "square.h"\n')
    output = tmp_path / "out.c"
    buildtool_cli.run([
        "read-sources",
        "squared._squared",
        str(cdef),
        str(csrc),
        str(output),
    ])
    generated = output.read_text()
    assert "square" in generated


def test_cli_read_sources_same_input_fails(capsys):
    with pytest.raises(SystemExit):
        buildtool_cli.run(["read-sources", "_squared", "-", "-", "-"])
    _stdout, stderr = capsys.readouterr()
    assert "are the same file and should not be" in stderr
