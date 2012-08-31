import api

ffi = api.PythonFFI()

referents = []
freelist = None

def store(x):
    global freelist
    if freelist is None:
        i = len(referents)
        referents.append(x)
    else:
        i = freelist = referents[freelist]
        referents[i] = x
    return i

def discard(i):
    global freelist
    referents[i] = freelist
    freelist = i

class Ref(object):
    def __init__(self, x):
        self.x = x
    def __enter__(self):
        self.i = i = store(self.x)
        return i
    def __exit__(self, *args):
        discard(self.i)

# ------------------------------------------------------------

ffi.cdef("""
    typedef int pyobj_t;
    int sum(pyobj_t oblist, int count);
""")

@ffi.pyexport("int(pyobj_t, int)")
def getitem(oblist, index):
    list = referents[oblist]
    return list[index]

lib = ffi.verify("""
    typedef int pyobj_t;

    int sum(pyobj_t oblist, int count) {
        int i, result = 0;
        for (i=0; i<count; i++) {
            int n = getitem(oblist, i);
            result += n;
        }
        return result;
    }
""")

with Ref([10, 20, 30, 40]) as oblist:
    print lib.sum(oblist, 4)
