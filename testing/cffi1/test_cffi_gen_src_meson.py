"""End-to-end test: build a self-contained CFFI extension with meson-python.

The test provisions a fresh nested venv under ``tmp_path`` using the
stdlib :mod:`venv` module, bridged so that it can import this
environment's ``cffi`` and ``meson-python`` (see
``testing.support.create_bridged_venv``), installs one of the small
example projects that live under ``testing/cffi1/cffi_gen_src_examples/``,
and then imports the built extension to confirm it works.

"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cffi

from testing.support import create_bridged_venv

pytestmark = [
    pytest.mark.thread_unsafe(reason="spawns subprocesses, slow"),
]

try:
    import mesonpy
except ImportError:
    pytest.skip("Test requires meson-python", allow_module_level=True)

# meson needs the ninja binary at build time; it is not a Python-level
# dependency of meson-python.
if not (shutil.which("ninja") or shutil.which("ninja-build")):
    pytest.skip("Test requires ninja", allow_module_level=True)


HERE = Path(__file__).resolve().parent
EXAMPLE_PROJECT = HERE / "cffi_gen_src_examples" / "exec_python_example"
EXAMPLE_PROJECT2 = HERE / "cffi_gen_src_examples" / "read_sources_example"


def _venv_python(venv_dir):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@pytest.mark.parametrize("project", [EXAMPLE_PROJECT, EXAMPLE_PROJECT2])
def test_meson_python_build(tmp_path, project):
    venv_dir = tmp_path / "venv"
    create_bridged_venv(venv_dir)
    venv_python = _venv_python(venv_dir)
    assert venv_python.exists(), venv_python

    # Copy the example project so nothing is written back into the
    # source tree
    project_dir = tmp_path / "project"
    shutil.copytree(project, project_dir)

    # --no-build-isolation so the build uses the bridged environment;
    # --no-index/--no-deps so pip cannot touch the network.
    proc = subprocess.run([
        str(venv_python), "-m", "pip", "install", "-v",
        "--no-index", "--no-deps", "--no-build-isolation", str(project_dir),
    ], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # Confirm the built extension imports and behaves as expected.
    subprocess.check_call([
        str(venv_python), "-c",
        "from squared import squared; "
        "assert squared(7) == 49; "
        "assert squared(-3) == 9",
    ])
