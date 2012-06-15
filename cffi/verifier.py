import os
from . import model, ffiplatform

class Verifier(object):

    def __init__(self, ffi):
        self.ffi = ffi
        self.typesdict = {}

    def prnt(self, what=''):
        print >> self.f, what

    def gettypenum(self, type):
        try:
            return self.typesdict[type]
        except KeyError:
            num = len(self.typesdict)
            self.typesdict[type] = num
            return num

    def verify(self, preamble, **kwds):
        modname = ffiplatform.undercffi_module_name()
        tmpdir = ffiplatform.tmpdir()
        filebase = os.path.join(tmpdir, modname)
        self.chained_list_constants = None
        
        with open(filebase + '.c', 'w') as f:
            self.f = f
            self.prnt(cffimod_header)
            self.prnt()
            self.prnt(preamble)
            self.prnt()
            #
            self.generate("decl")
            #
            self.prnt('static PyObject *_cffi_setup_custom(void)')
            self.prnt('{')
            self.prnt('  PyObject *dct = PyDict_New();')
            if self.chained_list_constants is not None:
                self.prnt('  if (dct == NULL)')
                self.prnt('    return NULL;')
                self.prnt('  if (%s(dct) < 0) {' % self.chained_list_constants)
                self.prnt('    Py_DECREF(dct);')
                self.prnt('    return NULL;')
                self.prnt('  }')
            self.prnt('  return dct;')
            self.prnt('}')
            self.prnt()
            #
            self.prnt('static PyMethodDef _cffi_methods[] = {')
            self.generate("method")
            self.prnt('  {"_cffi_setup", _cffi_setup, METH_VARARGS},')
            self.prnt('  {NULL, NULL}    /* Sentinel */')
            self.prnt('};')
            self.prnt()
            #
            self.prnt('PyMODINIT_FUNC')
            self.prnt('init%s(void)' % modname)
            self.prnt('{')
            self.prnt('  Py_InitModule("%s", _cffi_methods);' % modname)
            self.prnt('  _cffi_init();')
            self.prnt('}')
            #
            del self.f

        outputfilename = ffiplatform.compile(tmpdir, modname, **kwds)
        #
        import imp
        try:
            module = imp.load_dynamic(modname, outputfilename)
        except ImportError, e:
            raise ffiplatform.VerificationError(str(e))
        #
        self.load(module, 'loading')
        #
        revmapping = dict([(value, key)
                           for (key, value) in self.typesdict.items()])
        lst = [revmapping[i] for i in range(len(revmapping))]
        lst = map(self.ffi._get_cached_btype, lst)
        dct = module._cffi_setup(lst, ffiplatform.VerificationError)
        #
        class FFILibrary(object):
            pass
        library = FFILibrary()
        library.__dict__.update(dct)
        self.load(module, 'loaded', library=library)
        return library

    def generate(self, step_name):
        for name, tp in self.ffi._parser._declarations.iteritems():
            kind, realname = name.split(' ', 1)
            method = getattr(self, 'generate_cpy_%s_%s' % (kind, step_name))
            method(tp, realname)

    def load(self, module, step_name, **kwds):
        for name, tp in self.ffi._parser._declarations.iteritems():
            kind, realname = name.split(' ', 1)
            method = getattr(self, '%s_cpy_%s' % (step_name, kind))
            method(tp, realname, module, **kwds)

    def generate_nothing(self, tp, name):
        pass

    def loaded_noop(self, tp, name, module, **kwds):
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
        prnt('  _cffi_restore_errno();')
        prnt('  { %s%s(%s); }' % (
            result_code, name,
            ', '.join(['x%d' % i for i in range(len(tp.args))])))
        prnt('  _cffi_save_errno();')
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

    loading_cpy_function = loaded_noop

    def loaded_cpy_function(self, tp, name, module, library):
        setattr(library, name, getattr(module, name))

    # ----------
    # struct declarations

    def generate_cpy_struct_decl(self, tp, name):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        assert name == tp.name
        prnt = self.prnt
        checkfuncname = '_cffi_check_%s' % (name,)
        prnt('static void %s(struct %s *p)' % (checkfuncname, name))
        prnt('{')
        prnt('  /* only to generate compile-time warnings or errors */')
        for i in range(len(tp.fldnames)):
            fname = tp.fldnames[i]
            ftype = tp.fldtypes[i]
            if (isinstance(ftype, model.PrimitiveType)
                and ftype.is_integer_type()):
                # accept all integers, but complain on float or double
                prnt('  (void)((p->%s) << 1);' % fname)
            else:
                # only accept exactly the type declared.  Note the parentheses
                # around the '*tmp' below.  In most cases they are not needed
                # but don't hurt --- except test_struct_array_field.
                prnt('  { %s = &p->%s; (void)tmp; }' % (
                    ftype.get_c_name('(*tmp)'), fname))
        prnt('}')
        prnt('static PyObject *')
        prnt('_cffi_struct_%s(PyObject *self, PyObject *noarg)' % name)
        prnt('{')
        prnt('  struct _cffi_aligncheck { char x; struct %s y; };' % name)
        if tp.partial:
            prnt('  static Py_ssize_t nums[] = {')
            prnt('    sizeof(struct %s),' % name)
            prnt('    offsetof(struct _cffi_aligncheck, y),')
            for fname in tp.fldnames:
                prnt('    offsetof(struct %s, %s),' % (name, fname))
                prnt('    sizeof(((struct %s *)0)->%s),' % (name, fname))
            prnt('    -1')
            prnt('  };')
            prnt('  return _cffi_get_struct_layout(nums);')
        else:
            ffi = self.ffi
            BStruct = ffi._get_cached_btype(tp)
            conditions = [
                'sizeof(struct %s) != %d' % (name, ffi.sizeof(BStruct)),
                'offsetof(struct _cffi_aligncheck, y) != %d' % (
                    ffi.alignof(BStruct),)]
            for fname, ftype in zip(tp.fldnames, tp.fldtypes):
                BField = ffi._get_cached_btype(ftype)
                conditions += [
                    'offsetof(struct %s, %s) != %d' % (
                        name, fname, ffi.offsetof(BStruct, fname)),
                    'sizeof(((struct %s *)0)->%s) != %d' % (
                        name, fname, ffi.sizeof(BField))]
            prnt('  if (%s ||' % conditions[0])
            for i in range(1, len(conditions)-1):
                prnt('      %s ||' % conditions[i])
            prnt('      %s) {' % conditions[-1])
            prnt('    Py_INCREF(Py_False);')
            prnt('    return Py_False;')
            prnt('  }')
            prnt('  else {')
            prnt('    Py_INCREF(Py_True);')
            prnt('    return Py_True;')
            prnt('  }')
        prnt('  /* the next line is not executed, but compiled */')
        prnt('  %s(0);' % (checkfuncname,))
        prnt('}')
        prnt()

    def generate_cpy_struct_method(self, tp, name):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        self.prnt('  {"_cffi_struct_%s", _cffi_struct_%s, METH_NOARGS},' % (
            name, name))

    def loading_cpy_struct(self, tp, name, module):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        assert name == tp.name
        function = getattr(module, '_cffi_struct_%s' % name)
        layout = function()
        if layout is False:
            raise ffiplatform.VerificationError(
                "incompatible layout for struct %s" % name)
        elif layout is True:
            assert not tp.partial
        else:
            totalsize = layout[0]
            totalalignment = layout[1]
            fieldofs = layout[2::2]
            fieldsize = layout[3::2]
            assert len(fieldofs) == len(fieldsize) == len(tp.fldnames)
            tp.fixedlayout = fieldofs, fieldsize, totalsize, totalalignment

    def loaded_cpy_struct(self, tp, name, module, **kwds):
        if tp.fldnames is None:
            return     # nothing to do with opaque structs
        self.ffi._get_cached_btype(tp)   # force 'fixedlayout' to be considered

    # ----------
    # constants, likely declared with '#define'

    def _generate_chain_header(self, funcname, *vardecls):
        prnt = self.prnt
        prnt('static int %s(PyObject *dct)' % funcname)
        prnt('{')
        for decl in vardecls:
            prnt('  ' + decl)
        if self.chained_list_constants is not None:
            prnt('  if (%s(dct) < 0)' % self.chained_list_constants)
            prnt('    return -1;')
        self.chained_list_constants = funcname

    def _generate_cpy_const(self, is_int, name, tp=None, category='const'):
        vardecls = ['PyObject *o;',
                    'int res;']
        if not is_int:
            vardecls.append('%s;' % tp.get_c_name(' i'))
        else:
            assert category == 'const'
        self._generate_chain_header('_cffi_%s_%s' % (category, name),
                                    *vardecls)
        #
        prnt = self.prnt
        if not is_int:
            if category == 'var':
                realexpr = '&' + name
            else:
                realexpr = name
            prnt('  i = (%s);' % (realexpr,))
            prnt('  o = %s;' % (self.convert_expr_from_c(tp, 'i'),))
        else:
            prnt('  if (LONG_MIN <= (%s) && (%s) <= LONG_MAX)' % (name, name))
            prnt('    o = PyInt_FromLong((long)(%s));' % (name,))
            prnt('  else if ((%s) <= 0)' % (name,))
            prnt('    o = PyLong_FromLongLong((long long)(%s));' % (name,))
            prnt('  else')
            prnt('    o = PyLong_FromUnsignedLongLong('
                 '(unsigned long long)(%s));' % (name,))
        prnt('  if (o == NULL)')
        prnt('    return -1;')
        prnt('  res = PyDict_SetItemString(dct, "%s", o);' % name)
        prnt('  Py_DECREF(o);')
        prnt('  return res;')
        prnt('}')
        prnt()

    def generate_cpy_constant_decl(self, tp, name):
        is_int = isinstance(tp, model.PrimitiveType) and tp.is_integer_type()
        self._generate_cpy_const(is_int, name, tp)

    generate_cpy_constant_method = generate_nothing
    loading_cpy_constant = loaded_noop
    loaded_cpy_constant  = loaded_noop

    # ----------
    # enums

    def generate_cpy_enum_decl(self, tp, name):
        if tp.partial:
            for enumerator in tp.enumerators:
                self._generate_cpy_const(True, enumerator)
            return
        #
        self._generate_chain_header('_cffi_enum_%s' % name)
        prnt = self.prnt
        for enumerator, enumvalue in zip(tp.enumerators, tp.enumvalues):
            prnt('  if (%s != %d) {' % (enumerator, enumvalue))
            prnt('    PyErr_Format(_cffi_VerificationError,')
            prnt('                 "in enum %s: %s has the real value %d, '
                 'not %d",')
            prnt('                 "%s", "%s", (int)%s, %d);' % (
                name, enumerator, enumerator, enumvalue))
            prnt('    return -1;')
            prnt('  }')
        prnt('  return 0;')
        prnt('}')
        prnt()

    generate_cpy_enum_method = generate_nothing
    loading_cpy_enum = loaded_noop

    def loaded_cpy_enum(self, tp, name, module, library):
        if tp.partial:
            enumvalues = [getattr(library, enumerator)
                          for enumerator in tp.enumerators]
            tp.enumvalues = tuple(enumvalues)
            tp.partial = False
        else:
            for enumerator, enumvalue in zip(tp.enumerators, tp.enumvalues):
                setattr(library, enumerator, enumvalue)

    # ----------
    # macros: for now only for integers

    def generate_cpy_macro_decl(self, tp, name):
        assert tp == '...'
        self._generate_cpy_const(True, name)

    generate_cpy_macro_method = generate_nothing
    loading_cpy_macro = loaded_noop
    loaded_cpy_macro  = loaded_noop

    # ----------
    # global variables

    def generate_cpy_variable_decl(self, tp, name):
        tp_ptr = model.PointerType(tp)
        self._generate_cpy_const(False, name, tp_ptr, category='var')

    generate_cpy_variable_method = generate_nothing
    loading_cpy_variable = loaded_noop

    def loaded_cpy_variable(self, tp, name, module, library):
        # remove ptr=<cdata 'int *'> from the library instance, and replace
        # it by a property on the class, which reads/writes into ptr[0].
        ptr = getattr(library, name)
        delattr(library, name)
        def getter(library):
            return ptr[0]
        def setter(library, value):
            ptr[0] = value
        setattr(library.__class__, name, property(getter, setter))

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
#define _cffi_restore_errno                                              \
    ((void(*)(void))_cffi_exports[13])
#define _cffi_save_errno                                                 \
    ((void(*)(void))_cffi_exports[14])
#define _cffi_from_c_char                                                \
    ((PyObject *(*)(char))_cffi_exports[15])
#define _CFFI_NUM_EXPORTS 16

#if SIZEOF_LONG < SIZEOF_LONG_LONG
#  define _cffi_to_c_long_long PyLong_AsLongLong
#else
#  define _cffi_to_c_long_long _cffi_to_c_long
#endif

typedef struct _ctypedescr CTypeDescrObject;

static void *_cffi_exports[_CFFI_NUM_EXPORTS];
static PyObject *_cffi_types, *_cffi_VerificationError;

static PyObject *_cffi_setup_custom(void);   /* forward */

static PyObject *_cffi_setup(PyObject *self, PyObject *args)
{
    if (!PyArg_ParseTuple(args, "OO", &_cffi_types, &_cffi_VerificationError))
        return NULL;
    Py_INCREF(_cffi_types);
    Py_INCREF(_cffi_VerificationError);

    return _cffi_setup_custom();
}

static void _cffi_init(void)
{
    PyObject *module = PyImport_ImportModule("_ffi_backend");
    PyObject *c_api_object;

    if (module == NULL)
        return;

    c_api_object = PyObject_GetAttrString(module, "_C_API");
    if (c_api_object == NULL)
        return;
    if (!PyCObject_Check(c_api_object)) {
        PyErr_SetNone(PyExc_ImportError);
        return;
    }
    memcpy(_cffi_exports, PyCObject_AsVoidPtr(c_api_object),
           _CFFI_NUM_EXPORTS * sizeof(void *));
}

#define _cffi_type(num) ((CTypeDescrObject *)PyList_GET_ITEM(_cffi_types, num))

/**********/
'''
