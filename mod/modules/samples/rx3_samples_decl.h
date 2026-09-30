/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_SAMPLES_DECL_H
#define RX3_SAMPLES_DECL_H

#define SAMPLES_PAD_COUNT 8u
#define SAMPLES_MAX_VOICES 4u
#define SAMPLES_RATE 44100u
#define SAMPLES_CHANNELS 2u
#define SAMPLES_FRAME_BYTES 4u
#define SAMPLES_MIN_FRAMES 1u
#define SAMPLES_MAX_FRAMES (SAMPLES_RATE * 8u)
#define SAMPLES_BANK_MAX_BYTES 0x1000000u
#define SAMPLES_VOLUME_MAX 100u
#define SAMPLES_VOLUME_DEFAULT 50u
/* Per-pad trim, in percent of the sound as it was recorded. A kick and an
   airhorn are not the same loudness, and riding the on-screen strip to make up
   for it mid-set is not a control, it is a chore. Applied as plain amplitude
   rather than squared like the bank volume: this is a trim to match levels,
   where half means half, and the bank volume is the knob. */
#define SAMPLES_GAIN_UNITY 100u
#define SAMPLES_GAIN_MAX 200u
#define SAMPLES_CONFIG_MAX_BYTES 4096u
#define SAMPLES_CONFIG_VERSION 1u
#define SAMPLE_SLOT_IDLE 0xffffffffu

/* How a pad behaves once it is hit. Once is what every pad did before these
   existed, so a bank that names no mode plays exactly as it used to. */
#define SAMPLE_MODE_ONCE 0u
#define SAMPLE_MODE_HOLD 1u
#define SAMPLE_MODE_LOOP 2u
/* Started and stopped by the same pad, without looping. A bed or a long
   phrase could be fired but never taken back: once ignores the release and
   loop is the only mode that stops, so stopping meant SHIFT and losing the
   other seven with it. */
#define SAMPLE_MODE_LATCH 3u

struct samples_config {
    unsigned int volume;
    unsigned int colour[SAMPLES_PAD_COUNT];
    unsigned int mode[SAMPLES_PAD_COUNT];
    unsigned int gain[SAMPLES_PAD_COUNT];
    unsigned int shift_silence;
};

struct sample_slot {
    const int16_t *frames;
    unsigned int length;
    volatile unsigned int position; /* Packed generation/cursor; use the accessors below. */
    /* Copied from the config when the pad is hit rather than read in the
       mixer. The loader republishes the config when a bank is reloaded, and a
       sound already playing must not change what it is halfway through. */
    volatile unsigned int mode;
    volatile unsigned int gain;
};

/* 19 cursor bits cover the eight-second bank limit; the remaining bits
 * distinguish commands from an audio cursor update, including a retrigger at
 * zero. One CAS compares both. Input commands are serialized by the player. */
#define SAMPLE_CURSOR_MASK 0x7ffffu
#define SAMPLE_GENERATION_STEP 0x80000u
#if SAMPLES_MAX_FRAMES >= SAMPLE_CURSOR_MASK
#error Sample cursor cannot represent the configured bank limit
#endif
static inline unsigned int samples_voice_position(const struct sample_slot *voice)
{
    unsigned int cursor = __atomic_load_n(&voice->position, __ATOMIC_SEQ_CST) & SAMPLE_CURSOR_MASK;
    return cursor == SAMPLE_CURSOR_MASK ? SAMPLE_SLOT_IDLE : cursor;
}
static inline void samples_voice_command(struct sample_slot *voice, unsigned int cursor)
{
    unsigned int old = __atomic_load_n(&voice->position, __ATOMIC_SEQ_CST);
    for (;;) {
        unsigned int next = ((old + SAMPLE_GENERATION_STEP) & ~SAMPLE_CURSOR_MASK) |
                            (cursor & SAMPLE_CURSOR_MASK);
        if (__atomic_compare_exchange_n(&voice->position, &old, next, 0,
                                         __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) return;
    }
}

struct sample_bank_slot {
    const int16_t *frames;
    unsigned int length;
    void *block;
    size_t block_size;
};

#endif /* RX3_SAMPLES_DECL_H */
