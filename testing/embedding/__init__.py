import sys
import pytest

if sys.platform == "win32":
    pytest.skip("XXX fixme", allow_module_level=True)
