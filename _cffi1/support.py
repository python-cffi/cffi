
class U(object):
    def __add__(self, other):
        return eval('u'+repr(other).replace(r'\\u', r'\u')
                                   .replace(r'\\U', r'\U'))
u = U()
