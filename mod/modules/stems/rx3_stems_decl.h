/* SPDX-License-Identifier: MPL-2.0
 * Private Stems state and data formats used by its core adapters.
 */

#ifndef RX3_STEMS_DECL_H
#define RX3_STEMS_DECL_H

enum stem_mode {
    MODE_NONE = 0,
    MODE_INSTRUMENTAL = 1,
    MODE_VOCAL = 2,
    MODE_BOTH = MODE_INSTRUMENTAL | MODE_VOCAL
};

enum stem_format { FORMAT_F32 = 1, FORMAT_S16 = 2 };

struct __attribute__((packed)) stem_header {
    char magic[8];
    uint32_t sample_rate;
    uint32_t channels;
    uint32_t format;
    uint32_t header_size;
    uint64_t frames;
    uint8_t reserved[32];
};

struct stem_payload {
    const void *data;
    uint32_t format;
    uint64_t frames;
    void *block;
    size_t block_size;
};

struct stems_deck_context {
    void *volatile reader;
    volatile unsigned int status;
    volatile unsigned int selection;
    volatile uint32_t generation;
    volatile int armed;
    volatile unsigned int readers_active;
    float gain[4];
    float from[4];
    float target[4];
    unsigned int transition_cursor;
    unsigned int payload_count;
    struct stem_payload payloads[3];
    int pending_has_stem;
    int pending_fds[3];
    char pending_path[1024];
};

struct stems_load_request {
    struct stems_deck_context *context;
    void *reader;
    uint32_t generation;
    int fds[3];
};

static struct stems_deck_context stems_decks[2] = {
    {.pending_fds = {-1,-1,-1}}, {.pending_fds = {-1,-1,-1}}
};
static volatile unsigned int stems_callbacks_enabled;
static volatile unsigned int stems_callbacks_active;
static volatile unsigned int captured_pad_mask[2];
static const char *stems_dir;
static volatile unsigned int blink_origin;
static volatile unsigned int blink_origin_valid;

#endif /* RX3_STEMS_DECL_H */
