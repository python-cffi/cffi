import cffi

ffi = cffi.FFI()

ffi.embedding_api("")

ffi.set_source("_empty_cffi", """
CFFI_DLLEXPORT void initialize_my_empty_cffi(void) {
    if (cffi_start_python() != 0) {
        printf("oops, cffi_start_python() returned non-0\\n");
        abort();
    }
}
""")

fn = ffi.compile(verbose=True)
print('FILENAME: %s' % (fn,))
