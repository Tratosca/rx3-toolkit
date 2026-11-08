/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_AUDIO_API_H
#define RX3_AUDIO_API_H
#include "rx3_platform.h"
/* Typed audio stages. Each stage has one owner at a time; a second claim
 * fails without replacing the first. Processing runs on the player's audio
 * threads and must not allocate, perform I/O or wait. The core counts callers
 * in flight: release() detaches the native hook, drains admitted callbacks
 * and only then returns, so it must not be called from a callback. Buffers
 * belong to the player and are valid only during the call.
 */
struct rx3_stereo { float left, right; };

/* A deck's playback stream after speed and master tempo (TimeStretch), the
 * signal the deck actually plays. `position` is the reader frame of the first
 * output frame at 44.1 kHz; `reader` identifies the deck's current PcmReader
 * and changes with each track load. */
typedef void (*rx3_deck_stream_fn)(unsigned int deck, const void *reader, int position,
                                   struct rx3_stereo *output, unsigned int frames);
/* The master bus before the microphone talkover attenuator. */
typedef void (*rx3_master_fn)(struct rx3_stereo *output, unsigned int frames);

/* BEAT FX, on whichever bus it is assigned to (CH1, CH2 or MASTER), once per
 * block. capture() first rewrites a copy of the block that Roll and Slip Roll
 * record ahead of time; the bus is unchanged. send() then rewrites, in place,
 * the block the effect is about to process, and ret() gets that block back
 * from the effect. Blocks longer than RX3_BEAT_FX_CAPTURE_FRAMES are recorded
 * unchanged, without capture(). All three are required. */
#define RX3_BEAT_FX_CAPTURE_FRAMES 4096u
struct rx3_beat_fx_client {
    void (*capture)(struct rx3_stereo *block, unsigned int frames);
    void (*send)(struct rx3_stereo *block, unsigned int frames);
    void (*ret)(struct rx3_stereo *block, unsigned int frames);
};

struct rx3_audio_service {
    int (*claim_deck_stream)(const void *owner, rx3_deck_stream_fn);
    void (*release_deck_stream)(const void *owner);
    int (*claim_master)(const void *owner, rx3_master_fn);
    void (*release_master)(const void *owner);
    int (*claim_beat_fx)(const void *owner, const struct rx3_beat_fx_client *);
    void (*release_beat_fx)(const void *owner);
};
extern const struct rx3_audio_service rx3_audio;
#endif
