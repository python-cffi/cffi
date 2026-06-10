"""Entry point so ``python -m cffi.buildtool`` works.

The implementation is private; see ``cffi/_buildtool.py``.
"""

if __name__ == '__main__':
    from cffi._buildtool import run
    run()