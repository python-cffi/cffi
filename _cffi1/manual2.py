import _cffi_backend

ffi = _cffi_backend.FFI(b"manual2",
    _version = 0x2600,
    _types = b'\x00\x00\x01\x0D\x00\x00\x07\x01\x00\x00\x00\x0F\x00\x00\x00\x09\x00\x00\x00\x0B\x00\x00\x01\x03',
    _globals = (b'\x00\x00\x00#close',b'\x00\x00\x05#stdout'),
    _struct_unions = ((b'\x00\x00\x00\x03\x00\x00\x00\x00point_s',b'\x00\x00\x01\x11x',b'\x00\x00\x01\x11y'),),
    _enums = (b'\x00\x00\x00\x04\x00\x00\x00\x01myenum_e\x00AA,BB,CC',),
    _typenames = (b'\x00\x00\x00\x01myint_t',),
    _consts = {'AA':0,'BB':1,'CC':2},
)



# trying it out
lib = ffi.dlopen(None)
assert lib.BB == 1
x = lib.close(-42)
assert x == -1

print lib.stdout

print ffi.new("struct point_s *")
print ffi.offsetof("struct point_s", "x")
print ffi.offsetof("struct point_s", "y")

del ffi
