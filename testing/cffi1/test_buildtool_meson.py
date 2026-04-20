"""End-to-end test: build a self-contained CFFI extension with meson-python.

The test provisions a fresh nested venv under ``tmp_path`` using the
stdlib :mod:`venv` module, installs ``cffi`` (from the current source
tree) and ``meson-python`` into it, installs the small example project
that lives under ``testing/cffi1/buildtool_example/``, and then
imports the built extension to confirm it works.

The test does not use ``uv``. It only relies on the running Python
interpreter having access to ``pip`` (which is true for any venv
created by :mod:`venv`) and on a working C compiler being on ``PATH``.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import cffi

pytestmark = [
    pytest.mark.thread_unsafe(reason="spawns subprocesses, slow"),
]

try:
    import mesonpy
except ImportError:
    pytest.skip("Test requires meson-python", allow_module_level=True)


HERE = Path(__file__).resolve().parent
EXAMPLE_PROJECT = HERE / "buildtool_example"
EXAMPLE_PROJECT2 = HERE / "buildtool_example2"
CFFI_DIR = HERE.parent.parent


def _venv_python(venv_dir):
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


@pytest.mark.parametrize("project", [EXAMPLE_PROJECT, EXAMPLE_PROJECT2])
def test_meson_python_build(tmp_path, project):
    venv_dir = tmp_path / "venv"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
    venv_python = _venv_python(venv_dir)
    assert venv_python.exists(), venv_python

    # Upgrade pip so --no-build-isolation behaves consistently with recent
    # resolver behaviour on older base images.
    subprocess.check_call([
        str(venv_python), "-m", "pip", "install", "--upgrade", "pip",
    ])

    # Install build-time deps into the nested venv.
    subprocess.check_call([
        str(venv_python), "-m", "pip", "install", "meson-python", CFFI_DIR
    ])

    # Copy the example project so nothing is written back into the
    # source tree
    project_dir = tmp_path / "project"
    shutil.copytree(project, project_dir)

    # --no-build-isolation to ensure the test runs against the CFFI build we want to test
    subprocess.check_call([
        str(venv_python), "-m", "pip", "install",
        "--no-build-isolation", str(project_dir),
    ])

    # Confirm the built extension imports and behaves as expected.
    subprocess.check_call([
        str(venv_python), "-c",
        "from squared import squared; "
        "assert squared(7) == 49; "
        "assert squared(-3) == 9",
    ])
