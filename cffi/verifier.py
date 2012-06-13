import os
from . import model, ffiplatform

class Verifier(object):

    def __init__(self, ffi):
        self.ffi = ffi
        self.typesdict = {}

    def prnt(self, what=''):
        print >> self.f, what

    def gettypenum(self, type):
        BType = self.ffi._get_cached_btype(type)
        try:
            return self.typesdict[BType]
        except KeyError:
            num = len(self.typesdict)
            self.typesdict[BType] = num
            return num

    def verify(self, preamble, stop_on_warnings=True):
        modname = ffiplatform.undercffi_module_name()
        filebase = os.path.join(ffiplatform.tmpdir(), modname)
        
        with open(filebase + '.c', 'w') as f:
            self.f = f
            self.prnt(cffimod_header)
            self.prnt()
            self.prnt(preamble)
            self.prnt()
            #
            self.generate("decl")
            #
            self.prnt('static PyMethodDef _cffi_methods[] = {')
            self.generate("method")
            self.prnt('  {"_cffi_setup", _cffi_setup, METH_O},')
            self.prnt('  {NULL, NULL}    /* Sentinel */')
            self.prnt('};')
            self.prnt()
            #
            self.prnt('void init%s()' % modname)
            self.prnt('{')
            self.prnt('  Py_InitModule("%s", _cffi_methods);' % modname)
            self.prnt('  if (PyErr_Occurred() || _cffi_init()) return;')
            self.generate("init")
            self.prnt('}')
            #
            del self.f

        # XXX use more distutils?
        import distutils.sysconfig
        python_h = distutils.sysconfig.get_python_inc()
        cmdline = "gcc -I'%s' -O2 -shared -fPIC %s.c -o %s.so" % (
            python_h, filebase, filebase)
        if stop_on_warnings:
            cmdline += " -Werror"
        err = os.system(cmdline)
        if err:
            raise ffiplatform.VerificationError(
                '%s.c: see compilation errors above' % (filebase,))
        #
        import imp
        try:
            module = imp.load_dynamic(modname, '%s.so' % filebase)
        except ImportError, e:
            raise ffiplatform.VerificationError(str(e))
        #
        revmapping = dict([(value, key)
                           for (key, value) in self.typesdict.items()])
        lst = [revmapping[i] for i in range(len(revmapping))]
        module._cffi_setup(lst)
        del module._cffi_setup
        #
        self.load(module, 'loading')
        self.load(module, 'loaded')
        #
        return module

    def generate(self, step_name):
        for name, tp in self.ffi._parser._declarations.iteritems():
            kind, realname = name.split(' ', 1)
            method = getattr(self, 'generate_cpy_%s_%s' % (kind, step_name))
            method(tp, realname)

    def load(self, module, step_name):
        for name, tp in self.ffi._parser._declarations.iteritems():
            kind, realname = name.split(' ', 1)
            method = getattr(self, '%s_cpy_%s' % (step_name, kind))
            method(tp, realname, module)

    def generate_nothing(self, tp, name):
        pass

    def loaded_noop(self, tp, name, module):
        pass

    # ----------

    def convert_to_c(self, tp, fromvar, tovar, errcode, is_funcarg=False):
        extraarg = ''
        if isinstance(tp, model.PrimitiveType):
            converter = '_cffi_to_c_%s' % (tp.name.replace(' ', '_'),)
            errvalue = '-1'
        #
        elif isinstance(tp, model.PointerType):
            if (is_funcarg and
                    isinstance(tp.totype, model.PrimitiveType) and
                    tp.totype.name == 'char'):
                converter = '_cffi_to_c_char_p'
            else:
                converter = '(%s)_cffi_to_c_pointer' % tp.get_c_name('')
                extraarg = ', _cffi_type(%d)' % self.gettypenum(tp)
            errvalue = 'NULL'
        #
        else:
            raise NotImplementedError(tp)
        #
        self.prnt('  %s = %s(%s%s);' % (tovar, converter, fromvar, extraarg))
        self.prnt('  if (%s == (%s)%s && PyErr_Occurred())' % (
            tovar, tp.get_c_name(''), errvalue))
        self.prnt('    %s;' % errcode)

    def convert_expr_from_c(self, tp, var):
        if isinstance(tp, model.PrimitiveType):
            return '_cffi_from_c_%s(%s)' % (tp.name.replace(' ', '_'), var)
        elif isinstance(tp, model.PointerType):
            return '_cffi_from_c_pointer((char *)%s, _cffi_type(%d))' % (
                var, self.gettypenum(tp))
        else:
            raise NotImplementedError(tp)

    # ----------
    # typedefs: generates no code so far

    generate_cpy_typedef_decl   = generate_nothing
    generate_cpy_typedef_method = generate_nothing
    generate_cpy_typedef_init   = generate_nothing
    loading_cpy_typedef         = loaded_noop
    loaded_cpy_typedef          = loaded_noop

    # ----------
    # function declarations

    def generate_cpy_function_decl(self, tp, name):
        assert isinstance(tp, model.FunctionType)
        prnt = self.prnt
        numargs = len(tp.args)
        if numargs == 0:
            argname = 'no_arg'
        elif numargs == 1:
            argname = 'arg0'
        else:
            argname = 'args'
        prnt('static PyObject *')
        prnt('_cffi_f_%s(PyObject *self, PyObject *%s)' % (name, argname))
        prnt('{')
        assert not tp.ellipsis  # XXX later
        #
        for i, type in enumerate(tp.args):
            prnt('  %s;' % type.get_c_name(' x%d' % i))
        if not isinstance(tp.result, model.VoidType):
            result_code = 'result = '
            prnt('  %s;' % tp.result.get_c_name(' result'))
        else:
            result_code = ''
        #
        if len(tp.args) > 1:
            rng = range(len(tp.args))
            for i in rng:
                prnt('  PyObject *arg%d;' % i)
            prnt()
            prnt('  if (!PyArg_ParseTuple(args, "%s:%s", %s))' % (
                'O' * numargs, name, ', '.join(['&arg%d' % i for i in rng])))
            prnt('    return NULL;')
        prnt()
        #
        for i, type in enumerate(tp.args):
            self.convert_to_c(type, 'arg%d' % i, 'x%d' % i, 'return NULL',
                              is_funcarg=True)
            prnt()
        #
        prnt('  { %s%s(%s); }' % (
            result_code, name,
            ', '.join(['x%d' % i for i in range(len(tp.args))])))
        prnt()
        #
        if result_code:
            prnt('  return %s;' %
                 self.convert_expr_from_c(tp.result, 'result'))
        else:
            prnt('  Py_INCREF(Py_None);')
            prnt('  return Py_None;')
        prnt('}')
        prnt()

    def generate_cpy_function_method(self, tp, name):
        numargs = len(tp.args)
        if numargs == 0:
            meth = 'METH_NOARGS'
        elif numargs == 1:
            meth = 'METH_O'
        else:
            meth = 'METH_VARARGS'
        self.prnt('  {"%s", _cffi_f_%s, %s},' % (name, name, meth))

    generate_cpy_function_init = generate_nothing
    loading_cpy_function       = loaded_noop
    loaded_cpy_function        = loaded_noop

    # ----------
    # struct declarations

    def generate_cpy_struct_decl(self, tp, name):
        assert tp.partial    # xxx
        assert name == tp.name
        prnt = self.prnt
        prnt('static PyObject *')
        prnt('_cffi_struct_%s(PyObject *self, PyObject *noarg)' % name)
        prnt('{')
        prnt('  struct _cffi_aligncheck { char x; struct %s y; };' % name)
        prnt('  static Py_ssize_t nums[] = {')
        prnt('    sizeof(struct %s),' % name)
        prnt('    offsetof(struct _cffi_aligncheck, y),')
        for i in range(len(tp.fldnames)):
            prnt('    offsetof(struct %s, %s),' % (name, tp.fldnames[i]))
            prnt('    sizeof(((struct %s *)0)->%s),' % (name, tp.fldnames[i]))
        prnt('    -1')
        prnt('  };')
        prnt('  return _cffi_get_struct_layout(nums);')
        prnt('}')
        prnt()
        prnt('static void _cffi_check_%s(struct %s *p)' % (name, name))
        prnt('{')
        prnt('  /* only to generate compile-time warnings or errors */')
        for i in range(len(tp.fldnames)):
            fname = tp.fldnames[i]
            ftype = tp.fldtypes[i]
            if (isinstance(ftype, model.PrimitiveType)
                and ftype.is_integer_type()):
                # accept all integers, but complain on float or double
                prnt('  (p->%s) << 1;' % fname)
            else:
                # only accept exactly the type declared
                prnt('  { %s = &p->%s; }' % (
                    ftype.get_c_name('* tmp'), fname))
        prnt('}')

    def generate_cpy_struct_method(self, tp, name):
        self.prnt('  {"_cffi_struct_%s", _cffi_struct_%s, METH_NOARGS},' % (
            name, name))

    generate_cpy_struct_init = generate_nothing

    def loading_cpy_struct(self, tp, name, module):
        assert name == tp.name
        function = getattr(module, '_cffi_struct_%s' % name)
        layout = function()
        totalsize = layout[0]
        totalalignment = layout[1]
        fieldofs = layout[2::2]
        fieldsize = layout[3::2]
        assert len(fieldofs) == len(fieldsize) == len(tp.fldnames)
        tp.fixedlayout = fieldofs, fieldsize, totalsize, totalalignment

    def loaded_cpy_struct(self, tp, name, module):
        self.ffi._get_cached_btype(tp)   # force 'fixedlayout' to be considered

    # ----------


cffimod_header = r'''
#include <Python.h>
#include <stddef.h>

#define _cffi_from_c_double PyFloat_FromDouble
#define _cffi_from_c_float PyFloat_FromDouble
#define _cffi_from_c_signed_char PyInt_FromLong
#define _cffi_from_c_short PyInt_FromLong
#define _cffi_from_c_int PyInt_FromLong
#define _cffi_from_c_long PyInt_FromLong
#define _cffi_from_c_unsigned_char PyInt_FromLong
#define _cffi_from_c_unsigned_short PyInt_FromLong
#define _cffi_from_c_unsigned_long PyLong_FromUnsignedLong
#define _cffi_from_c_unsigned_long_long PyLong_FromUnsignedLongLong

#if SIZEOF_INT < SIZEOF_LONG
#  define _cffi_from_c_unsigned_int PyInt_FromLong
#else
#  define _cffi_from_c_unsigned_int PyLong_FromUnsignedLong
#endif

#if SIZEOF_LONG < SIZEOF_LONG_LONG
#  define _cffi_from_c_long_long PyLong_FromLongLong
#else
#  define _cffi_from_c_long_long PyInt_FromLong
#endif

static PyObject *_cffi_from_c_char(char x) {
    return PyString_FromStringAndSize(&x, 1);
}

#define _cffi_to_c_long PyInt_AsLong
#define _cffi_to_c_double PyFloat_AsDouble
#define _cffi_to_c_float PyFloat_AsDouble

#define _cffi_to_c_char_p                                                \
                 ((char *(*)(PyObject *))_cffi_exports[0])
#define _cffi_to_c_signed_char                                           \
                 ((signed char(*)(PyObject *))_cffi_exports[1])
#define _cffi_to_c_unsigned_char                                         \
                 ((unsigned char(*)(PyObject *))_cffi_exports[2])
#define _cffi_to_c_short                                                 \
                 ((short(*)(PyObject *))_cffi_exports[3])
#define _cffi_to_c_unsigned_short                                        \
                 ((unsigned short(*)(PyObject *))_cffi_exports[4])

#if SIZEOF_INT < SIZEOF_LONG
#  define _cffi_to_c_int                                                 \
                   ((int(*)(PyObject *))_cffi_exports[5])
#  define _cffi_to_c_unsigned_int                                        \
                   ((unsigned int(*)(PyObject *))_cffi_exports[6])
#else
#  define _cffi_to_c_int          _cffi_to_c_long
#  define _cffi_to_c_unsigned_int _cffi_to_c_unsigned_long
#endif

#define _cffi_to_c_unsigned_long                                         \
                 ((unsigned long(*)(PyObject *))_cffi_exports[7])
#define _cffi_to_c_unsigned_long_long                                    \
                 ((unsigned long long(*)(PyObject *))_cffi_exports[8])
#define _cffi_to_c_char                                                  \
                 ((char(*)(PyObject *))_cffi_exports[9])
#define _cffi_from_c_pointer                                             \
    ((PyObject *(*)(char *, CTypeDescrObject *))_cffi_exports[10])
#define _cffi_to_c_pointer                                               \
    ((char *(*)(PyObject *, CTypeDescrObject *))_cffi_exports[11])
#define _cffi_get_struct_layout                                          \
    ((PyObject *(*)(Py_ssize_t[]))_cffi_exports[12])

#if SIZEOF_LONG < SIZEOF_LONG_LONG
#  define _cffi_to_c_long_long PyLong_AsLongLong
#else
#  define _cffi_to_c_long_long _cffi_to_c_long
#endif

typedef struct _ctypedescr CTypeDescrObject;

static void **_cffi_exports;
static PyObject *_cffi_types;

static int _cffi_init(void)
{
    PyObject *module = PyImport_ImportModule("_ffi_backend");
    PyObject *c_api_object;

    if (module == NULL)
        return -1;

    c_api_object = PyObject_GetAttrString(module, "_C_API");
    if (c_api_object == NULL)
        return -1;
    if (!PyCObject_Check(c_api_object)) {
        PyErr_SetNone(PyExc_ImportError);
        return -1;
    }
    _cffi_exports = (void **)PyCObject_AsVoidPtr(c_api_object);
    return 0;
}

static PyObject *_cffi_setup(PyObject *self, PyObject *arg)
{
    Py_INCREF(arg);
    _cffi_types = arg;
    Py_INCREF(Py_None);
    return Py_None;
}

#define _cffi_type(num) ((CTypeDescrObject *)PyList_GET_ITEM(_cffi_types, num))

/**********/
'''
