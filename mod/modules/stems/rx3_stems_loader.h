/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_LOADER_H
#define RX3_STEMS_LOADER_H

#include "rx3_stems_package.h"

/* Loads run as jobs on the core's shared loader. The pending slot per deck
   keeps only the newest request; a job takes whatever is pending. */
static volatile unsigned int stems_queue_lock;
static struct stems_load_request *stems_pending_loads[2];

static void stems_lock(void)
{
    while (__atomic_exchange_n(&stems_queue_lock, 1u, __ATOMIC_SEQ_CST)) usleep(1000u);
}

static void stems_unlock(void)
{
    __atomic_store_n(&stems_queue_lock, 0u, __ATOMIC_SEQ_CST);
}

static void stems_drain(struct stems_deck_context *context)
{
    for (;;) {
        while (__atomic_load_n(&context->readers_active, __ATOMIC_SEQ_CST)) usleep(1000u);
        usleep(10000u);
        if (!__atomic_load_n(&context->readers_active, __ATOMIC_SEQ_CST)) return;
    }
}

static void stems_release_request(struct stems_load_request *request)
{
    if (!request) return;
    for (unsigned int i = 0; i < 3u; i++) if (request->fds[i] >= 0) close(request->fds[i]);
    munmap(request, 4096u);
}

static int stems_load_payload(int fd, struct stem_payload *destination,
                               unsigned int other_bytes, const struct stems_io *io)
{
    struct stem_header header;
    off_t size = lseek(fd, 0, SEEK_END);
    if (size < (off_t)sizeof(header) || lseek(fd, 0, SEEK_SET) != 0 ||
        stems_read(fd, &header, sizeof(header), io)) return 0;
    if (!stems_pcm_gain(&header) || memcmp(header.magic, "RX3STM1\0", 8u) ||
        header.sample_rate != 44100u || header.channels != 2u || header.header_size != 64u ||
        !header.frames || header.frames > RX3_STEMS_MAX_FRAMES ||
        header.frames * 4u + 64u != (uint64_t)size) return 0;
    size_t bytes = (size_t)header.frames * 4u;
    if (other_bytes >= RX3_STEMS_RESIDENT_BYTES || bytes > RX3_STEMS_RESIDENT_BYTES - other_bytes)
        return 0;
    /* The player keeps its reserve; the shared ledger counts what other
       modules are allocating at this moment. */
    const struct rx3_memory_service *memory = framework->memory;
    if (!memory->reserve(&stems_decks, bytes, RX3_STEMS_PLAYER_RESERVE_KIB)) return 0;
    void *block = mmap(0, bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (block == MAP_FAILED) {
        memory->abandon(&stems_decks, bytes);
        return 0;
    }
    if (stems_read(fd, block, bytes, io) || mprotect(block, bytes, PROT_READ)) {
        munmap(block, bytes);
        memory->abandon(&stems_decks, bytes);
        return 0;
    }
    memory->settle(&stems_decks, bytes);
    destination->data = block;
    destination->format = header.format;
    destination->pcm_gain = stems_pcm_gain(&header);
    destination->frames = header.frames;
    destination->block = block;
    destination->block_size = bytes;
    return 1;
}

/* The worker is single-threaded. The other deck can release memory while
   this set loads, but cannot allocate a second pending set concurrently. */
static unsigned int stems_load_set(const int fds[3], struct stem_payload next[3],
                                    unsigned int other_bytes, const struct stems_io *io)
{
    unsigned int count = 0u;
    while (count < 3u && fds[count] >= 0) count++;
    unsigned int resident = other_bytes;
    for (unsigned int i = 0; i < count; i++) {
        if (!stems_load_payload(fds[i], &next[i], resident, io) ||
            (i && next[i].frames != next[0].frames)) {
            release_payload(&next[i]);
            return i; /* Preserve the validated prefix instead of reading it again. */
        }
        resident += next[i].block_size;
    }
    return count;
}

static int stems_loader_stopping(void)
{
    return framework->loader->stopping(&stems_decks);
}

static int stems_request_cancelled(const void *opaque)
{
    const struct stems_load_request *request = opaque;
    return stems_loader_stopping() ||
        __atomic_load_n(&request->context->generation, __ATOMIC_SEQ_CST) != request->generation;
}

/* A loader job: every pending request, newest per deck, then return. */
static void stems_load_pending(void *unused)
{
    (void)unused;
    while (!stems_loader_stopping()) {
        struct stems_load_request *request = 0;
        stems_lock();
        for (unsigned int deck = 0; deck < 2u; deck++)
            if (stems_pending_loads[deck]) {
                request = stems_pending_loads[deck];
                stems_pending_loads[deck] = 0;
                break;
            }
        stems_unlock();
        if (!request) return;
        struct stems_deck_context *context = request->context;
        const struct stems_io io = {stems_request_cancelled, request};
        struct stem_payload next[3] = {0};
        unsigned int count = 0u;
        while (count < 3u && request->fds[count] >= 0) count++;
        unsigned int wanted = count;
        stems_lock();
        struct stems_deck_context *other = &stems_decks[context == &stems_decks[0] ? 1u : 0u];
        unsigned int other_bytes = 0u;
        for (unsigned int j = 0; j < other->payload_count; j++)
            other_bytes += other->payloads[j].block_size;
        stems_unlock();
        char magic[8];
        int packaged = lseek(request->fds[0], 0, SEEK_SET) == 0 &&
            !stems_read(request->fds[0], magic, 8u, &io) && !memcmp(magic, "RX3PKG2\0", 8u);
        count = stems_io_cancelled(&io) ? 0u :
            packaged ? stems_package_load(request->fds[0], next, other_bytes, &io)
                     : stems_load_set(request->fds, next, other_bytes, &io);
        if (packaged && count) log_line("stems package: package verified");
        stems_lock();
        if (!stems_request_cancelled(request) &&
            context->reader == request->reader) {
            if (count) {
                __atomic_store_n(&context->reader, 0, __ATOMIC_SEQ_CST);
                stems_drain(context);
                for (unsigned int i = 0; i < 3u; i++) release_payload(&context->payloads[i]);
                memcpy(context->payloads, next, sizeof(next));
                memset(next, 0, sizeof(next));
                context->payload_count = count;
                unsigned int available = (2u << count) - 1u;
                unsigned int old = __atomic_load_n(&context->selection, __ATOMIC_SEQ_CST);
                __atomic_store_n(&context->selection,
                                  ((old & ~255u) + 256u) | available * 17u, __ATOMIC_SEQ_CST);
                stems_set_mask(context, available);
                __atomic_store_n(&context->reader, request->reader, __ATOMIC_SEQ_CST);
                __atomic_store_n(&context->status, 2u, __ATOMIC_SEQ_CST);
                log_number("stems ready, available roles = ", count + 1u);
                if (count < wanted) log_line("stems reduced: an additional stem was rejected");
            } else {
                __atomic_store_n(&context->armed, 0, __ATOMIC_SEQ_CST);
                __atomic_store_n(&context->status, 3u, __ATOMIC_SEQ_CST);
                log_line("stems rejected: no valid resident set");
            }
        }
        stems_unlock();
        for (unsigned int i = 0; i < 3u; i++) release_payload(&next[i]);
        stems_release_request(request);
    }
}

static void stems_feature_track_will_load(unsigned int deck, void *reader,
                                          const void *track_info)
{
    (void)reader;
    if (deck >= 2u) return;
    struct stems_deck_context *context = &stems_decks[deck];
    stems_lock();
    __atomic_add_fetch(&context->generation, 1u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&context->reader, 0, __ATOMIC_SEQ_CST);
    for (unsigned int i = 0; i < 3u; i++) {
        if (context->pending_fds[i] >= 0) close(context->pending_fds[i]);
        context->pending_fds[i] = -1;
    }
    context->pending_path[0] = 0;
    if (!stem_path_for_track(track_info, context->pending_path, sizeof(context->pending_path))) {
        static const char *suffix[3] = {".rx3stem", ".rx3drums", ".rx3bass"};
        char path[1024];
        size_t prefix = str_length(context->pending_path) - 8u;
        memcpy(path, context->pending_path, prefix);
        for (unsigned int i = 0; i < 3u; i++) {
            size_t size = str_length(suffix[i]) + 1u;
            if (prefix + size > sizeof(path)) break;
            memcpy(path + prefix, suffix[i], size);
            context->pending_fds[i] = open(path, O_RDONLY);
        }
    }
    context->pending_has_stem = context->pending_fds[0] >= 0;
    stems_unlock();
}

static void stems_feature_track_did_load(unsigned int deck, void *reader,
                                         const void *track_info)
{
    (void)track_info;
    if (deck >= 2u) return;
    struct stems_deck_context *context = &stems_decks[deck];
    stems_lock();
    __atomic_store_n(&context->reader, 0, __ATOMIC_SEQ_CST);
    __atomic_add_fetch(&context->generation, 1u, __ATOMIC_SEQ_CST);
    stems_drain(context);
    for (unsigned int i = 0; i < 3u; i++) release_payload(&context->payloads[i]);
    context->payload_count = 0u;
    stems_reset_mix(context);
    captured_pad_mask[deck] = 0u;
#ifdef RX3_OVERCUE_PROTOTYPE
    if(getenv("RX3_OVERCUE_ROOT")) {
        for(unsigned int i=0;i<3u;i++) {
            if(context->pending_fds[i]>=0)close(context->pending_fds[i]);
            context->pending_fds[i]=-1;
        }
        context->overcue=1u;
        rx3_overcue_track(deck,(const char *)track_info);
        __atomic_store_n(&context->selection,0x77u,__ATOMIC_SEQ_CST);
        stems_set_mask(context,7u);
        __atomic_store_n(&context->armed,1u,__ATOMIC_SEQ_CST);
        __atomic_store_n(&context->status,1u,__ATOMIC_SEQ_CST);
        __atomic_store_n(&context->reader,reader,__ATOMIC_SEQ_CST);
        stems_unlock();return;
    }
#endif
    unsigned int count = 0u;
    while (count < 3u && context->pending_fds[count] >= 0) count++;
    unsigned int available = count ? (2u << count) - 1u : 0u;
    unsigned int old = __atomic_load_n(&context->selection, __ATOMIC_SEQ_CST);
    __atomic_store_n(&context->selection, ((old & ~255u) + 256u) | available * 17u, __ATOMIC_SEQ_CST);
    stems_set_mask(context, available);
    __atomic_store_n(&context->armed, count != 0u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&context->status, count ? 1u : 0u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&context->reader, reader, __ATOMIC_SEQ_CST);
    struct stems_load_request *request = count ? mmap(0, 4096u, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0) : MAP_FAILED;
    if (request != MAP_FAILED) {
        request->context = context;
        request->reader = reader;
        request->generation = __atomic_load_n(&context->generation, __ATOMIC_SEQ_CST);
        for (unsigned int i = 0; i < 3u; i++) {
            request->fds[i] = context->pending_fds[i];
            context->pending_fds[i] = -1;
        }
        stems_release_request(stems_pending_loads[deck]);
        stems_pending_loads[deck] = request;
    } else {
        for (unsigned int i = 0; i < 3u; i++) {
            if (context->pending_fds[i] >= 0) close(context->pending_fds[i]);
            context->pending_fds[i] = -1;
        }
        if (count) {
            context->armed = 0;
            context->status = 3u;
        }
    }
    stems_unlock();
    if (request != MAP_FAILED) {
        const struct rx3_load_job job = {stems_load_pending, 0, 0};
        if (!framework->loader->submit(&stems_decks, &job))
            log_line("stems: loader queue full, the load waits for the next job");
    }
}

#endif /* RX3_STEMS_LOADER_H */
