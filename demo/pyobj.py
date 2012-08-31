import api

ffi = api.PythonFFI()

referents = []     # list "object descriptor -> python object"
freelist = None

def store(x):
    "Store the object 'x' and returns a new object descriptor for it."
    global freelist
    if freelist is None:
        i = len(referents)
        referents.append(x)
    else:
        i = freelist
        freelist = referents[freelist]
        referents[i] = x
    return i

def discard(i):
    "Discard (i.e. close) the object descriptor 'i'."
    global freelist
    referents[i] = freelist
    freelist = i

class Ref(object):
    """For use in 'with Ref(x) as ob': open an object descriptor
    and returns it in 'ob', and close it automatically when the
    'with' statement finishes."""
    def __init__(self, x):
        self.x = x
    def __enter__(self):
        self.i = i = store(self.x)
        return i
    def __exit__(self, *args):
        discard(self.i)

def count_pyobj_alive():
    result = len(referents)
    i = freelist
    while i is not None:
        assert result > 0
        result -= 1
        i = referents[i]
    return result

# ------------------------------------------------------------

ffi.cdef("""
    typedef int pyobj_t;
    int sum_integers(pyobj_t oblist);
    pyobj_t sum_objects(pyobj_t oblist, pyobj_t obinitial);
""")

@ffi.pyexport("int(pyobj_t)")
def length(oblist):
    list = referents[oblist]
    return len(list)

@ffi.pyexport("int(pyobj_t, int)")
def getitem(oblist, index):
    list = referents[oblist]
    return list[index]

@ffi.pyexport("pyobj_t(pyobj_t)")
def pyobj_dup(ob):
    return store(referents[ob])

@ffi.pyexport("void(pyobj_t)")
def pyobj_close(ob):
    discard(ob)

@ffi.pyexport("pyobj_t(pyobj_t, int)")
def pyobj_getitem(oblist, index):
    list = referents[oblist]
    return store(list[index])

@ffi.pyexport("pyobj_t(pyobj_t, pyobj_t)")
def pyobj_add(ob1, ob2):
    return store(referents[ob1] + referents[ob2])

lib = ffi.verify("""
    typedef int pyobj_t;    /* an "object descriptor" number */

    int sum_integers(pyobj_t oblist) {
        /* this a demo function written in C, using the API
           defined above: length() and getitem(). */
        int i, result = 0;
        int count = length(oblist);
        for (i=0; i<count; i++) {
            int n = getitem(oblist, i);
            result += n;
        }
        return result;
    }

    pyobj_t sum_objects(pyobj_t oblist, pyobj_t obinitial) {
        /* same as above, but keeps all additions as Python objects */
        int i;
        int count = length(oblist);
        pyobj_t ob = pyobj_dup(obinitial);
        for (i=0; i<count; i++) {
            pyobj_t ob2 = pyobj_getitem(oblist, i);
            pyobj_t ob3 = pyobj_add(ob, ob2);
            pyobj_close(ob2);
            pyobj_close(ob);
            ob = ob3;
        }
        return ob;
    }
""")

with Ref([10, 20, 30, 40]) as oblist:
    print lib.sum_integers(oblist)
    with Ref(0) as obinitial:
        obresult = lib.sum_objects(oblist, obinitial)
        print referents[obresult]
        discard(obresult)

assert not count_pyobj_alive()
