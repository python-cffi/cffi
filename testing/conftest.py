import pytest
import sys

from ctypes import util

try:
    import pytest_run_parallel  # noqa:F401
    PARALLEL_RUN_AVAILABLE = True
except Exception:
    PARALLEL_RUN_AVAILABLE = False

def pytest_configure(config):
    # Don't warn for `pytest-run-parallel` markers if they're not available
    if not PARALLEL_RUN_AVAILABLE:
        config.addinivalue_line(
            'markers',
            'parallel_threads(n): run the given test function in parallel '
            'using `n` threads.')
        config.addinivalue_line(
            "markers",
            "thread_unsafe: mark the test function as single-threaded",
        )
        config.addinivalue_line(
            "markers",
            "iterations(n): run the given test function `n` times in each thread",
        )

# this problem was supposedly fixed in a newer Python 3.8 release, but after binary installer support expired
# https://github.com/python/cpython/pull/28054
if sys.platform == 'darwin' and sys.version_info[:2] == (3, 8):
    orig_find_library = util.find_library

    def hacked_find_library(*args, **kwargs):
        res = orig_find_library(*args, **kwargs)

        if res is None:
            pytest.xfail("busted find_library on MacOS Python 3.8")

        return res

    util.find_library = hacked_find_library
