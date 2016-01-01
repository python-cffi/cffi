#include <stdio.h>
#include <pthread.h>
#include <semaphore.h>
#include <assert.h>

#define NTHREADS 10


extern int add1(int, int);

static sem_t done;


static void *start_routine(void *arg)
{
    int x, y, status;
    x = add1(40, 2);
    assert(x == 42);

    status = sem_post(&done);
    assert(status == 0);

    return arg;
}

int main(void)
{
    pthread_t th;
    int i, status = sem_init(&done, 0, 0);
    assert(status == 0);

    printf("starting\n");
    for (i = 0; i < NTHREADS; i++) {
        status = pthread_create(&th, NULL, start_routine, NULL);
        assert(status == 0);
    }
    for (i = 1; i <= NTHREADS; i++) {
        status = sem_wait(&done);
        assert(status == 0);
    }
    printf("done\n");
    return 0;
}
