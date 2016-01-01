#include <stdio.h>

extern int add_rec(int, int);
extern int (*my_callback)(int);

static int some_callback(int x)
{
    printf("some_callback(%d)\n", x);
    return add_rec(x, 9);
}

int main(void)
{
    int x, y;
    my_callback = some_callback;
    x = add_rec(40, 2);
    y = add_rec(100, -5);
    printf("got: %d %d\n", x, y);
    return 0;
}
