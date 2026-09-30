/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_platform.h"
#include "../api/rx3_memory_api.h"
#include "rx3_memory.h"

static unsigned long meminfo_value(const char *buffer, ssize_t count, const char *key)
{
    size_t key_length = 0;
    while (key[key_length]) key_length++;
    for (ssize_t i = 0; i + (ssize_t)key_length < count; i++) {
        if (memcmp(buffer + i, key, key_length))
            continue;
        ssize_t j = i + (ssize_t)key_length;
        while (j < count && (buffer[j] == ' ' || buffer[j] == '\t'))
            j++;
        unsigned long value = 0;
        while (j < count && buffer[j] >= '0' && buffer[j] <= '9')
            value = value * 10u + (unsigned long)(buffer[j++] - '0');
        return value;
    }
    return 0;
}

/* Immediately available or reclaimable RAM in KiB. */
unsigned long rx3_memory_available_kb(void)
{
    char buffer[2048];
    int fd = open("/proc/meminfo", O_RDONLY);
    if (fd < 0)
        return 0;
    ssize_t count = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (count <= 0)
        return 0;
    buffer[count] = '\0';
    /* Linux 3.0.101 has no MemAvailable field. Fall back to a conservative
       estimate from free, buffer, and cache pages. */
    unsigned long available = meminfo_value(buffer, count, "MemAvailable:");
    if (available)
        return available;
    return meminfo_value(buffer, count, "MemFree:") +
           meminfo_value(buffer, count, "Buffers:") +
           meminfo_value(buffer, count, "Cached:");
}

/* In-flight bytes are reserved but not yet resident: the kernel does not
   count them, so every other owner must. Settled bytes are already in the
   kernel's figure and are only recorded. A small spin lock serializes the
   ledger; its holders never block inside it. */
#define LEDGER_OWNERS 8u
struct entry { const void *owner; unsigned long in_flight, held; };
static struct entry ledger[LEDGER_OWNERS];
static volatile unsigned int ledger_lock;

static void lock(void) { while (__atomic_exchange_n(&ledger_lock, 1u, __ATOMIC_SEQ_CST)) usleep(100u); }
static void unlock(void) { __atomic_store_n(&ledger_lock, 0u, __ATOMIC_SEQ_CST); }

static struct entry *find(const void *owner, int create)
{
    struct entry *free_entry = 0;
    for (unsigned int i = 0; i < LEDGER_OWNERS; i++) {
        if (ledger[i].owner == owner) return &ledger[i];
        if (!ledger[i].owner && !free_entry) free_entry = &ledger[i];
    }
    if (create && free_entry) free_entry->owner = owner;
    return create ? free_entry : 0;
}

static unsigned long kib(unsigned long bytes) { return bytes / 1024u + (bytes % 1024u != 0u); }

static int reserve(const void *owner, unsigned long bytes, unsigned long floor_kb)
{
    if (!owner || !bytes) return 0;
    /* Read outside the lock: /proc can be slow, and it answers for the
       settled allocations already. */
    unsigned long available = floor_kb ? rx3_memory_available_kb() : 0;
    lock();
    struct entry *own = find(owner, 1);
    if (!own) { unlock(); return 0; }
    unsigned long others = 0;
    for (unsigned int i = 0; i < LEDGER_OWNERS; i++)
        if (ledger[i].owner && &ledger[i] != own) others += kib(ledger[i].in_flight);
    int granted = !floor_kb ||
        (available > floor_kb + others && available - floor_kb - others >= kib(bytes));
    if (granted) own->in_flight += bytes;
    unlock();
    return granted;
}

static void move(const void *owner, unsigned long bytes, int settle, int release)
{
    lock();
    struct entry *own = find(owner, 0);
    if (own) {
        if (release) {
            own->held -= bytes < own->held ? bytes : own->held;
        } else {
            unsigned long taken = bytes < own->in_flight ? bytes : own->in_flight;
            own->in_flight -= taken;
            if (settle) own->held += taken;
        }
    }
    unlock();
}

static void settle(const void *owner, unsigned long bytes) { move(owner, bytes, 1, 0); }
static void abandon(const void *owner, unsigned long bytes) { move(owner, bytes, 0, 0); }
static void release(const void *owner, unsigned long bytes) { move(owner, bytes, 0, 1); }

static unsigned long held(void)
{
    unsigned long total = 0;
    lock();
    for (unsigned int i = 0; i < LEDGER_OWNERS; i++) total += ledger[i].held;
    unlock();
    return total;
}

const struct rx3_memory_service rx3_memory = {
    reserve, settle, abandon, release, rx3_memory_available_kb, held
};
