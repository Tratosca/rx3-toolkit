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

enum sidecar_format { FORMAT_F32 = 1, FORMAT_S16 = 2 };

struct __attribute__((packed)) sidecar_header {
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
    volatile void *reader;
    volatile enum stem_mode mode;
    volatile uint32_t generation;
    volatile int armed;
    enum stem_mode rendered_mode;
    enum stem_mode transition_from;
    enum stem_mode transition_to;
    unsigned int transition_cursor;
    struct stem_payload vocal;
    int pending_has_sidecar;
    char pending_path[1024];
};

struct stems_load_request {
    struct stems_deck_context *context;
    void *reader;
    uint32_t generation;
    char path[1024];
};

static struct stems_deck_context stems_decks[2];
static volatile unsigned int captured_pad_mask[2];
static const char *stems_dir;
static volatile unsigned int blink_origin;
static volatile unsigned int blink_origin_valid;

#endif /* RX3_STEMS_DECL_H */
