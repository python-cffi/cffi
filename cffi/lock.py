import sys

if sys.version_info < (3,):
    try:
        from thread import allocate_lock
    except ImportError:
        from dummy_thread import allocate_lock
else:
    try:
        from _thread import allocate_lock
    except ImportError:
        from _dummy_thread import allocate_lock
