from ._squared import ffi, lib


def squared(n):
    return lib.square(n)
