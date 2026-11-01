/* SPDX-License-Identifier: MPL-2.0
 * Private Stems state and data formats, compiled by rx3_stems_module.c.
 */

#ifndef RX3_STEMS_DECL_H
#define RX3_STEMS_DECL_H

#include "rx3_stems_limits.h"
#ifdef RX3_OVERCUE_PROTOTYPE
#include "overcue/overcue.h"
#endif

typedef struct { int16_t left, right; } Short2;

/* Crossfade length when a role is switched, in valid frames. */
#define TRANSITION_FRAMES 256u
/* The longest beat an echo repeats: 60 BPM. A slower grid is halved. */
#define STEMS_ECHO_FRAMES 44100u


enum stem_mode {
    MODE_NONE = 0,
    MODE_INSTRUMENTAL = 1,
    MODE_VOCAL = 2,
    MODE_BOTH = MODE_INSTRUMENTAL | MODE_VOCAL
};

enum stem_format { FORMAT_F32 = 1, FORMAT_S16 = 2, FORMAT_S16_GAIN = 3 };

struct __attribute__((packed)) stem_header {
    char magic[8];
    uint32_t sample_rate;
    uint32_t channels;
    uint32_t format;
    uint32_t header_size;
    uint64_t frames;
    uint8_t reserved[32];
};

static float stems_pcm_gain(const struct stem_header *h)
{
    if(h->format==FORMAT_S16) {
        for(unsigned int i=0;i<32;i++) if(h->reserved[i]) return 0;
        return 1.0f;
    }
    if(h->format!=FORMAT_S16_GAIN) return 0;
    float gain;
    memcpy(&gain,h->reserved,4);
    if(!(gain>=1.0f && gain<=64.0f)) return 0;
    for(unsigned int i=4;i<32;i++) if(h->reserved[i]) return 0;
    return gain;
}

struct stem_payload {
    const void *data;
    uint32_t format;
    float pcm_gain;
    uint64_t frames;
    void *block;
    size_t block_size;
    const uint8_t *wave;
    unsigned int wave_size;
};

/* A role repeating the beat before `origin`. Owned by the audio thread;
   `frames` is nonzero while it rings, and the pad lights read it. All three
   positions are track frames: `press` starts the repeats and moves with a jump,
   `leave` is where a role came back. */
struct stems_echo_tail {
    volatile unsigned int frames;
    int origin, press, leave, leaving;
    float level;
};

struct stems_deck_context {
#ifdef RX3_OVERCUE_PROTOTYPE
    unsigned int overcue;
#endif
    void *volatile reader;
    volatile unsigned int status;
    volatile unsigned int selection;
    /* Four 7-bit percentages; one atomic snapshot for buttons and audio. */
    volatile uint32_t levels;
    volatile uint32_t generation;
    volatile int armed;
    volatile unsigned int readers_active;
    float gain[4];
    float from[4];
    float target[4];
    unsigned int transition_cursor;
    unsigned int payload_count;
    struct stem_payload payloads[3];
    /* A pad asks; the audio thread answers at its next block. */
    volatile unsigned int echo_request;
    volatile unsigned int echo_frames;
    volatile unsigned int echo_level[3];
    /* The track frames the history holds, and where the last block ended. */
    int echo_low, echo_high, echo_valid, echo_next;
    struct stems_echo_tail echo[3];
    /* Reported by the watcher: what the last press read. */
    volatile unsigned int echo_report;
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
static volatile unsigned int captured_pad_mask[2];
static const char *stems_dir;

/* Nonzero while one of these role bits is asked for or still ringing. */
static unsigned int stems_echo_running(const struct stems_deck_context *context,
                                       unsigned int bits)
{
    unsigned int running = __atomic_load_n(&context->echo_request, __ATOMIC_SEQ_CST);
    for (unsigned int i = 0; i < 3u; i++)
        if (__atomic_load_n(&context->echo[i].frames, __ATOMIC_SEQ_CST)) running |= 1u << i;
    return running & bits;
}

#endif /* RX3_STEMS_DECL_H */
