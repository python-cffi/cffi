import py
import sys
import os
import atexit


# This is copied from PyPy's vendored py lib.  The latest py lib release
# (1.8.1) contains a bug and crashes if it sees another temporary directory
# in which we don't have write permission (e.g. because it's owned by someone
# else).
def make_numbered_dir(prefix='session-', rootdir=None, keep=3,
                      lock_timeout = 172800,   # two days
                      min_timeout = 300):      # five minutes
    """ return unique directory with a number greater than the current
        maximum one.  The number is assumed to start directly after prefix.
        if keep is true directories with a number less than (maxnum-keep)
        will be removed.
    """
    if rootdir is None:
        rootdir = py.path.local.get_temproot()

    def parse_num(path):
        """ parse the number out of a path (if it matches the prefix) """
        bn = path.basename
        if bn.startswith(prefix):
            try:
                return int(bn[len(prefix):])
            except ValueError:
                pass

    # compute the maximum number currently in use with the
    # prefix
    lastmax = None
    while True:
        maxnum = -1
        for path in rootdir.listdir():
            num = parse_num(path)
            if num is not None:
                maxnum = max(maxnum, num)

        # make the new directory
        try:
            udir = rootdir.mkdir(prefix + str(maxnum+1))
        except py.error.EEXIST:
            # race condition: another thread/process created the dir
            # in the meantime.  Try counting again
            if lastmax == maxnum:
                raise
            lastmax = maxnum
            continue
        break

    # put a .lock file in the new directory that will be removed at
    # process exit
    if lock_timeout:
        lockfile = udir.join('.lock')
        mypid = os.getpid()
        if hasattr(lockfile, 'mksymlinkto'):
            lockfile.mksymlinkto(str(mypid))
        else:
            lockfile.write(str(mypid))
        def try_remove_lockfile():
            # in a fork() situation, only the last process should
            # remove the .lock, otherwise the other processes run the
            # risk of seeing their temporary dir disappear.  For now
            # we remove the .lock in the parent only (i.e. we assume
            # that the children finish before the parent).
            if os.getpid() != mypid:
                return
            try:
                lockfile.remove()
            except py.error.Error:
                pass
        atexit.register(try_remove_lockfile)

    # prune old directories
    if keep:
        for path in rootdir.listdir():
            num = parse_num(path)
            if num is not None and num <= (maxnum - keep):
                if min_timeout:
                    # NB: doing this is needed to prevent (or reduce
                    # a lot the chance of) the following situation:
                    # 'keep+1' processes call make_numbered_dir() at
                    # the same time, they create dirs, but then the
                    # last process notices the first dir doesn't have
                    # (yet) a .lock in it and kills it.
                    try:
                        t1 = path.lstat().mtime
                        t2 = lockfile.lstat().mtime
                        if abs(t2-t1) < min_timeout:
                            continue   # skip directories too recent
                    except py.error.Error:
                        continue   # failure to get a time, better skip
                lf = path.join('.lock')
                try:
                    t1 = lf.lstat().mtime
                    t2 = lockfile.lstat().mtime
                    if not lock_timeout or abs(t2-t1) < lock_timeout:
                        continue   # skip directories still locked
                except py.error.Error:
                    pass   # assume that it means that there is no 'lf'
                try:
                    path.remove(rec=1)
                except KeyboardInterrupt:
                    raise
                except: # this might be py.error.Error, WindowsError ...
                    pass

    # make link...
    try:
        username = os.environ['USER']           #linux, et al
    except KeyError:
        try:
            username = os.environ['USERNAME']   #windows
        except KeyError:
            username = 'current'

    src  = str(udir)
    dest = src[:src.rfind('-')] + '-' + username
    try:
        os.unlink(dest)
    except OSError:
        pass
    try:
        os.symlink(src, dest)
    except (OSError, AttributeError, NotImplementedError):
        pass

    return udir


udir = make_numbered_dir(prefix = 'ffi-')


# Windows-only workaround for some configurations: see
# https://bugs.python.org/issue23246 (Python 2.7.9)
if sys.platform == 'win32':
    try:
        import setuptools
    except ImportError:
        pass
