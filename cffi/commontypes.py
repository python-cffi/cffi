from . import api, model


COMMON_TYPES = {
    'FILE': model.unknown_type('FILE', '_IO_FILE'),
    'bool': model.PrimitiveType('_Bool'),
    }

for _type in model.PrimitiveType.ALL_PRIMITIVE_TYPES:
    if _type.endswith('_t'):
        COMMON_TYPES[_type] = model.PrimitiveType(_type)
del _type
