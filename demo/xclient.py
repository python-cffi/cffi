import sys
sys.path.append('.')
try:
    import _xclient
except ImportError:
    from cffi import FFI
    _ffi = FFI()
    _ffi.cdef("""

    typedef ... Display;
    typedef struct { ...; } Window;

    typedef struct { int type; ...; } XEvent;

    Display *XOpenDisplay(char *display_name);
    Window DefaultRootWindow(Display *display);
    int XMapRaised(Display *display, Window w);
    Window XCreateSimpleWindow(Display *display, Window parent, int x, int y,
                               unsigned int width, unsigned int height,
                               unsigned int border_width, unsigned long border,
                               unsigned long background);
    int XNextEvent(Display *display, XEvent *event_return);
    """)

    _ffi.set_source('_xclient', """
                #include <X11/Xlib.h>
    """, libraries=['X11'])
    _ffi.compile()
    import _xclient

ffi = _xclient.ffi
lib = _xclient.lib

class XError(Exception):
    pass

def main():
    display = lib.XOpenDisplay(ffi.NULL)
    if display == ffi.NULL:
        raise XError("cannot open display")
    w = lib.XCreateSimpleWindow(display, lib.DefaultRootWindow(display),
                            10, 10, 500, 350, 0, 0, 0)
    lib.XMapRaised(display, w)
    event = ffi.new("XEvent *")
    lib.XNextEvent(display, event)

if __name__ == '__main__':
    main()
