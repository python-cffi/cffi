import sys, cffi


ffi = cffi.FFI()

ffi.embedding_api("""
    int add1(int, int);
""")

ffi.embedding_init_code("""
    import sys, time
    for c in '""" + chr(0x00ff) + chr(0x1234) + chr(0xfedc) + """':
        sys.stdout.write(str(ord(c)) + '\\n')
    sys.stdout.flush()
""")

ffi.set_source("_withunicode_cffi", """
""")

fn = ffi.compile(verbose=True)
print('FILENAME: %s' % (fn,))
