
typedef struct {
    PyObject_HEAD

    CTypeDescrObject *gs_type;
    char             *gs_data;

} GlobSupportObject;

static void glob_support_dealloc(GlobSupportObject *gs)
{
    Py_DECREF(gs->gs_type);
    PyObject_Del(gs);
}

static PyTypeObject GlobSupport_Type = {
    PyVarObject_HEAD_INIT(NULL, 0)
    "FFIGlobSupport",
    sizeof(GlobSupportObject),
    0,
    (destructor)glob_support_dealloc,           /* tp_dealloc */
    0,                                          /* tp_print */
    0,                                          /* tp_getattr */
    0,                                          /* tp_setattr */
    0,                                          /* tp_compare */
    0,                                          /* tp_repr */
    0,                                          /* tp_as_number */
    0,                                          /* tp_as_sequence */
    0,                                          /* tp_as_mapping */
    0,                                          /* tp_hash */
    0,                                          /* tp_call */
    0,                                          /* tp_str */
    PyObject_GenericGetAttr,                    /* tp_getattro */
    0,                                          /* tp_setattro */
    0,                                          /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT,                         /* tp_flags */
};

#define GlobSupport_Check(ob)  (Py_TYPE(ob) == &GlobSupport_Type)

static PyObject *make_global_var(CTypeDescrObject *type, char *addr)
{
    GlobSupportObject *gs = PyObject_New(GlobSupportObject, &GlobSupport_Type);
    if (gs == NULL)
        return NULL;

    Py_INCREF(type);
    gs->gs_type = type;
    gs->gs_data = addr;
    return (PyObject *)gs;
}

static PyObject *read_global_var(GlobSupportObject *gs)
{
    return convert_to_object(gs->gs_data, gs->gs_type);
}

static int write_global_var(GlobSupportObject *gs, PyObject *obj)
{
    return convert_from_object(gs->gs_data, gs->gs_type, obj);
}

static PyObject *cg_addressof_global_var(GlobSupportObject *gs)
{
    PyObject *x, *ptrtype = new_pointer_type(gs->gs_type);
    if (ptrtype == NULL)
        return NULL;

    x = new_simple_cdata(gs->gs_data, (CTypeDescrObject *)ptrtype);
    Py_DECREF(ptrtype);
    return x;
}
