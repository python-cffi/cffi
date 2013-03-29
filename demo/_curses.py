"""Very partial replacement of the standard extension module '_curses'.
Just contains the minimal amount of stuff to make one of my curses
programs run.  XXX should also check for and report errors.
"""
from cffi import FFI

ffi = FFI()


ffi.cdef("""
typedef ... WINDOW;
typedef unsigned char bool;
typedef unsigned long chtype;
static const int ERR, OK;

WINDOW *initscr(void);
int endwin(void);
bool isendwin(void);

const char *keyname(int c);
static const int KEY_MIN, KEY_MAX;

int setupterm(char *term, int fildes, int *errret);

int tigetflag(char *);
int tigetnum(char *);
char *tigetstr(char *);
char *tparm (const char *, ...);

int cbreak(void);
int nocbreak(void);
int echo(void);
int noecho(void);
int keypad(WINDOW *win, bool bf);
int notimeout(WINDOW *win, bool bf);
void wtimeout(WINDOW *win, int delay);

int def_prog_mode(void);
int def_shell_mode(void);
int reset_prog_mode(void);
int reset_shell_mode(void);
int resetty(void);
int savetty(void);
void getsyx(int y, int x);
void setsyx(int y, int x);
//int ripoffline(int line, int (*init)(WINDOW *, int));
int curs_set(int visibility);
int napms(int ms);

int start_color(void);
int init_pair(short pair, short f, short b);
int init_color(short color, short r, short g, short b);
bool has_colors(void);
bool can_change_color(void);
int color_content(short color, short *r, short *g, short *b);
int pair_content(short pair, short *f, short *b);

int use_default_colors(void);

static const int COLOR_BLACK;
static const int COLOR_RED;
static const int COLOR_GREEN;
static const int COLOR_YELLOW;
static const int COLOR_BLUE;
static const int COLOR_MAGENTA;
static const int COLOR_CYAN;
static const int COLOR_WHITE;

static const int A_ATTRIBUTES;
static const int A_NORMAL;
static const int A_STANDOUT;
static const int A_UNDERLINE;
static const int A_REVERSE;
static const int A_BLINK;
static const int A_DIM;
static const int A_BOLD;
static const int A_ALTCHARSET;
static const int A_INVIS;
static const int A_PROTECT;
static const int A_CHARTEXT;
static const int A_COLOR;

int COLORS, COLOR_PAIRS;

void _m_getyx(WINDOW *win, int yx[2]);
void _m_getparyx(WINDOW *win, int yx[2]);
void _m_getbegyx(WINDOW *win, int yx[2]);
void _m_getmaxyx(WINDOW *win, int yx[2]);

int wclear(WINDOW *win);
int wclrtoeol(WINDOW *win);
int wmove(WINDOW *win, int y, int x);
int waddstr(WINDOW *win, const char *str);
int mvwaddstr(WINDOW *win, int y, int x, const char *str);
void wbkgdset(WINDOW *win, chtype ch);
int wrefresh(WINDOW *win);
int wgetch(WINDOW *win);

int getattrs(WINDOW *win);
int wattrset(WINDOW *win, int attrs);
""")


lib = ffi.verify("""
#include <ncurses.h>
#include <term.h>

void _m_getyx(WINDOW *win, int yx[2]) {
    getyx(win, yx[0], yx[1]);
}
void _m_getparyx(WINDOW *win, int yx[2]) {
    getparyx(win, yx[0], yx[1]);
}
void _m_getbegyx(WINDOW *win, int yx[2]) {
    getbegyx(win, yx[0], yx[1]);
}
void _m_getmaxyx(WINDOW *win, int yx[2]) {
    getmaxyx(win, yx[0], yx[1]);
}
""",
                 libraries=['ncurses'])


def _setup():
    globals().update(lib.__dict__)
    for key in range(KEY_MIN, KEY_MAX):
        key_n = keyname(key)
        if key_n == ffi.NULL or ffi.string(key_n) == "UNKNOWN KEY":
            continue
        key_n = ffi.string(key_n).replace('(', '').replace(')', '')
        globals()[key_n] = key

_setup()

# ____________________________________________________________

class error(Exception):
    pass

class Window(object):
    def __init__(self):
        self._window = lib.initscr()

    def getyx(self):
        yx = ffi.new("int[2]")
        lib._m_getyx(self._window, yx)
        return tuple(yx)

    def getparyx(self):
        yx = ffi.new("int[2]")
        lib._m_getparyx(self._window, yx)
        return tuple(yx)

    def getbegyx(self):
        yx = ffi.new("int[2]")
        lib._m_getbegyx(self._window, yx)
        return tuple(yx)

    def getmaxyx(self):
        yx = ffi.new("int[2]")
        lib._m_getmaxyx(self._window, yx)
        return tuple(yx)

    def addstr(self, *args):
        y = None
        attr = None
        if len(args) == 1:
            text, = args
        elif len(args) == 2:
            text, attr = args
        elif len(args) == 3:
            y, x, text = args
        elif len(args) == 4:
            y, x, text, attr = args
        else:
            raise TypeError("addstr requires 1 to 4 arguments")
        if attr is not None:
            attr_old = getattrs(self._window)
            wattrset(self._window, attr)
        if y is not None:
            mvwaddstr(self._window, y, x, text)
        else:
            waddstr(self._window, text)
        if attr is not None:
            wattrset(self._window, attr_old)

    def bkgdset(self, bkgd, attr=A_NORMAL):
        if isinstance(bkgd, str):
            bkgd = ord(bkgd)
        wbkgdset(self._window, bkgd | attr)


    def _make_method(cname):
        method = getattr(lib, cname)
        def _execute(self, *args):
            return method(self._window, *args)
        return _execute

    keypad     = _make_method('keypad')
    clear      = _make_method('wclear')
    clrtoeol   = _make_method('wclrtoeol')
    move       = _make_method('wmove')
    refresh    = _make_method('wrefresh')
    getch      = _make_method('wgetch')
    notimeout  = _make_method('notimeout')
    timeout    = _make_method('wtimeout')

    del _make_method


initscr = Window

_setupterm_called = False


def _ensure_setupterm_called():
    if not _setupterm_called:
        raise error("must call (at least) setupterm() first")


def setupterm(term=None, fd=-1):
    if term is None:
        term = ffi.NULL
    if fd < 0:
        import sys
        fd = sys.stdout.fileno()
    err = ffi.new("int *")
    if lib.setupterm(term, fd, err) == ERR:
        if err[0] == 0:
            s = "setupterm: could not find terminal"
        elif err[0] == 1:
            s = "setupterm: could not find terminfo database"
        else:
            s = "setupterm: unknown error %d" % err[0]
        raise error(s)
    global _setupterm_called
    _setupterm_called = True


def tigetflag(capname):
    _ensure_setupterm_called()
    return lib.tigetflag(capname)


def tigetnum(capname):
    _ensure_setupterm_called()
    return lib.tigetnum(capname)


def tigetstr(capname):
    _ensure_setupterm_called()
    out = lib.tigetstr(capname)
    if out == ffi.NULL:
        return None
    return ffi.string(out)


def tparm(name, *args):
    _ensure_setupterm_called()
    cargs = [ffi.cast("long", arg) for arg in args]
    return ffi.string(lib.tparm(name, *cargs))


def color_pair(n):
    return n << 8
