/* SPDX-License-Identifier: MPL-2.0 */
/* The shared loading worker. It polls a small ring rather than waiting on a
 * condition: the player's libc offers no condition variable the hook may
 * import, and loads are rare enough that a 10 ms idle tick costs nothing. */
#include "../api/rx3_platform.h"
#include "../api/rx3_loader_api.h"
#include "rx3_loader.h"
#include "rx3_log.h"

#define QUEUE 16u
#define OWNERS 4u
struct slot { const void *owner; struct rx3_load_job job; };
static struct slot queue[QUEUE];
static unsigned int head, count;
static const void *owners[OWNERS];
static const void *volatile stopping_owners[OWNERS];
static const void *volatile running_owner;
static volatile unsigned int queue_lock, worker_running;
static pthread_t worker;
static int worker_started;

static void lock(void) { while (__atomic_exchange_n(&queue_lock, 1u, __ATOMIC_SEQ_CST)) usleep(100u); }
static void unlock(void) { __atomic_store_n(&queue_lock, 0u, __ATOMIC_SEQ_CST); }

static int claimed(const void *owner)
{
    for (unsigned int i = 0; i < OWNERS; i++) if (owners[i] == owner) return 1;
    return 0;
}

static int is_stopping(const void *owner)
{
    for (unsigned int i = 0; i < OWNERS; i++)
        if (__atomic_load_n(&stopping_owners[i], __ATOMIC_SEQ_CST) == owner) return 1;
    return 0;
}

static void *work(void *unused)
{
    (void)unused;
    while (__atomic_load_n(&worker_running, __ATOMIC_SEQ_CST)) {
        struct slot next = {0, {0, 0, 0}};
        lock();
        if (count) {
            next = queue[head];
            head = (head + 1u) % QUEUE;
            count--;
            /* Published inside the lock, so release() cannot miss it. */
            __atomic_store_n(&running_owner, next.owner, __ATOMIC_SEQ_CST);
        }
        unlock();
        if (!next.owner) { usleep(10000u); continue; }
        next.job.run(next.job.context);
        __atomic_store_n(&running_owner, 0, __ATOMIC_SEQ_CST);
    }
    return 0;
}

static int claim(const void *owner)
{
    if (!owner || claimed(owner)) return 0;
    unsigned int at = OWNERS;
    for (unsigned int i = 0; i < OWNERS && at == OWNERS; i++) if (!owners[i]) at = i;
    if (at == OWNERS) return 0;
    if (!worker_started) {
        __atomic_store_n(&worker_running, 1u, __ATOMIC_SEQ_CST);
        if (pthread_create(&worker, 0, work, 0)) {
            worker_running = 0u;
            log_line("loader: worker could not start");
            return 0;
        }
        worker_started = 1;
    }
    owners[at] = owner;
    return 1;
}

static int submit(const void *owner, const struct rx3_load_job *job)
{
    if (!owner || !job || !job->run || !claimed(owner) || is_stopping(owner)) return 0;
    lock();
    int accepted = count < QUEUE;
    if (accepted) {
        queue[(head + count) % QUEUE] = (struct slot){owner, *job};
        count++;
    }
    unlock();
    return accepted;
}

static void release(const void *owner)
{
    if (!owner || !claimed(owner)) return;
    unsigned int mark = OWNERS;
    for (unsigned int i = 0; i < OWNERS && mark == OWNERS; i++)
        if (!stopping_owners[i]) mark = i;
    if (mark < OWNERS) __atomic_store_n(&stopping_owners[mark], owner, __ATOMIC_SEQ_CST);
    /* Take the owner's queued jobs out, keeping everyone else's order. */
    struct rx3_load_job dropped[QUEUE];
    unsigned int dropped_count = 0, kept = 0;
    lock();
    for (unsigned int i = 0; i < count; i++) {
        struct slot entry = queue[(head + i) % QUEUE];
        if (entry.owner == owner) dropped[dropped_count++] = entry.job;
        else queue[(head + kept++) % QUEUE] = entry;
    }
    count = kept;
    unlock();
    for (unsigned int i = 0; i < dropped_count; i++)
        if (dropped[i].discard) dropped[i].discard(dropped[i].context);
    while (__atomic_load_n(&running_owner, __ATOMIC_SEQ_CST) == owner) usleep(1000u);
    for (unsigned int i = 0; i < OWNERS; i++) if (owners[i] == owner) owners[i] = 0;
    if (mark < OWNERS) __atomic_store_n(&stopping_owners[mark], 0, __ATOMIC_SEQ_CST);
    int anyone = 0;
    for (unsigned int i = 0; i < OWNERS; i++) anyone |= owners[i] != 0;
    if (!anyone && worker_started) {
        __atomic_store_n(&worker_running, 0u, __ATOMIC_SEQ_CST);
        pthread_join(worker, 0);
        worker_started = 0;
    }
}

unsigned int rx3_loader_pending(void)
{
    lock();
    unsigned int n = count;
    unlock();
    return n;
}

const struct rx3_loader_service rx3_loader = {claim, submit, is_stopping, release};
