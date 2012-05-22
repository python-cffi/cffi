

class BackendBase(object):

    def __init__(self):
        self._cached_btypes = {}

    def nonstandard_integer_types(self):
        return {}

    def get_cached_btype(self, methname, *args):
        try:
            BType = self._cached_btypes[methname, args]
        except KeyError:
            BType = getattr(self, methname)(*args)
            self._cached_btypes[methname, args] = BType
        return BType
