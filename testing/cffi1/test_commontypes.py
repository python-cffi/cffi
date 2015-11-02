import py, os, cffi
import _cffi_backend


def test_alphabetical_order():
    f = open(os.path.join(os.path.dirname(cffi.__file__),
                          '..', 'c', 'commontypes.c'))
    lines = [line for line in f.readlines() if line.strip().startswith('EQ(')]
    f.close()
    assert lines == sorted(lines)

def test_get_common_types():
    d = {}
    _cffi_backend._get_common_types(d)
    assert d["bool"] == "_Bool"
