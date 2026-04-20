# Integrated from the cffi-buildtool project by Rose Davidson
# (https://github.com/inklesspen/cffi-buildtool), MIT-licensed.
"""
Entrypoint module, in case you use `python -m cffi.buildtool`.


Why does this file exist, and why __main__? For more info, read:

- https://www.python.org/dev/peps/pep-0338/
- https://docs.python.org/2/using/cmdline.html#cmdoption-m
- https://docs.python.org/3/using/cmdline.html#cmdoption-m
"""


from ._cli import run

if __name__ == '__main__':
    run()
