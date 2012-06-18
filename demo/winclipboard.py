from cffi import FFI

ffi = FFI()
ffi.cdef('''
    typedef void * HANDLE;
    typedef HANDLE HWND;
    typedef int BOOL;
    typedef unsigned int UINT;
    typedef int SIZE_T;
    typedef char * LPTSTR;
    typedef HANDLE HGLOBAL;
    typedef HANDLE LPVOID;
   
    HWND GetConsoleWindow(void);

    LPVOID GlobalLock( HGLOBAL hMem );
    BOOL GlobalUnlock( HGLOBAL hMem );
    HGLOBAL GlobalAlloc(UINT uFlags, SIZE_T dwBytes);
   
    BOOL  OpenClipboard(HWND hWndNewOwner);
    BOOL  CloseClipboard(void);
    BOOL  EmptyClipboard(void);
    HANDLE  SetClipboardData(UINT uFormat, HANDLE hMem);
   
    void * memcpy(void * s1, void * s2, int n);
    ''')
   
lib = ffi.verify('''
    #include <windows.h>
''', libraries=["user32"])

def PutToClipboard(string):
    CF_TEXT=1
    GMEM_MOVEABLE = 0x0002

    hWnd = lib.GetConsoleWindow()
 
    if lib.OpenClipboard(hWnd):
        cstring = ffi.new("char[]", string)

        # make it a moveable memory for other processes
        hGlobal = lib.GlobalAlloc(GMEM_MOVEABLE, size)
        buffer = lib.GlobalLock(hGlobal)
        lib.memcpy(buffer, cstring, size)
        lib.GlobalUnlock(hGlobal)
       
        res = lib.EmptyClipboard()
        res = lib.SetClipboardData(CF_TEXT, buffer)
 
        lib.CloseClipboard()
       
PutToClipboard("this string from cffi")
