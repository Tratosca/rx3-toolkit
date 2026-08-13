/* SPDX-License-Identifier: MPL-2.0
 *
 * Key shift for the RX3 performance runtime: declarations.
 *
 * Included by the core hook before it defines its shared machinery. The code
 * itself is in rx3_keyshift.h, which the core includes once its logging, hook
 * installer and deck table exist.
 *
 * The XDJ-RX3 has no key shift. Two engines provide it here, and they are
 * selected by direction because each is measured to fail where the other
 * succeeds -- see README.md in this directory.
 */

#ifndef RX3_KEYSHIFT_DECL_H
#define RX3_KEYSHIFT_DECL_H

#define TIMESTRETCH_STREAM ((unsigned long)0x000c292c)
/* dsp::TimeStretchScratch::operate is the live playback producer: hardware
   tracing showed every call to the TimeStretch wrapper coming from inside it,
   scratching or not, because it also carries varispeed. It reads overlapping
   source windows through that wrapper and resamples them, so its output -- not
   its input -- is the deck's block stream, and that is where a sequential DSP
   belongs. It derives from TimeStretch, so +4 is still the reader. */
#define TIMESTRETCH_OPERATE ((unsigned long)0x000a22a0)
/* dsp::TimeStretchFGPR::operate replaces the one above while Master Tempo is
   on: the two are mutually exclusive, which is why the shift simply vanished
   with key lock engaged instead of sounding wrong. Same contract, same base. */
#define TIMESTRETCH_FGPR_OPERATE ((unsigned long)0x000a73bc)

#define PITCH_CTOR       ((unsigned long)0x0008b700)
#define PITCH_DTOR       ((unsigned long)0x0008b420)
#define PITCH_INITIALIZE ((unsigned long)0x0008b2b8)
#define PITCH_EXECUTE    ((unsigned long)0x0008c648)
/* mixerengine::BeatEffect::adjustParameter is the base-class entry the stock
   mixer uses. It clamps the value, stores it, and dispatches the subclass
   recalculation, so it is the only path that leaves BeatEffectPitch in a
   coherent state. Parameter 2 is level/depth, parameter 4 the percentage. */
#define PITCH_ADJUST_PARAMETER ((unsigned long)0x000b5b38)
#define PITCH_PARAM_LEVEL_DEPTH 2
#define PITCH_PARAM_PERCENT     4
/* changePercentValuePitch scales the percentage by a curve driven by
   level/depth. 0.5 is its exact unity point: the shift speed is then
   percent/100, so -50 .. +100 is exactly -12 .. +12 semitones. */
#define PITCH_UNITY_LEVEL_DEPTH 0.5f

#include "rx3_pitch_shift.h"


#define PITCH_MAX_FRAMES 8192u

#define RX3_ENABLE_PITCH 1
/* The two shifters fail in opposite places, measured on a 440 Hz tone as the
   share of output energy left on the note:
 *
 *            -12    -7    -5    +5    +7   +12
 *   stock      --  99.9  99.9  52.7  15.8  84.6
 *   ours     43.6  69.4  99.7  99.0  97.3  93.8
 *
 * So each direction gets the one that wins it. Lowering pitch skips material
 * and the stock effect handles that cleanly; raising it repeats material, which
 * is where the stock grain splices fall apart and ours does not.
 * RX3_USE_NATIVE_PITCH forces one for both directions, for listening tests. */
#define RX3_HYBRID_PITCH 1
#define RX3_USE_NATIVE_PITCH 0

/* Private key-shift state. It deliberately does not share the stems module's
   deck structure: both features know a deck only through the core's index. */
struct rx3_keyshift_deck {
    volatile int semitones;
    volatile int pitch_pending;
    volatile unsigned int pitch_tail_blocks;
    void *pitch;
    Float2 *pitch_output;
    struct rx3_shifter shifter;
};

static struct rx3_keyshift_deck keyshift_decks[2];
static int keyshift_enabled;

typedef unsigned long (*timestretch_stream_fn)(void *, long, Float2 *,
                                              unsigned int);
typedef long (*timestretch_operate_fn)(void *, long, Float2 *,
                                      unsigned int);

typedef void *(*pitch_ctor_fn)(void *);
typedef void *(*pitch_dtor_fn)(void *);
typedef void (*pitch_initialize_fn)(void *);
typedef void (*pitch_adjust_fn)(void *, int, float);
typedef void (*pitch_execute_fn)(void *, const Float2 *, Float2 *, int);

static const uint8_t timestretch_stream_guard[8] = {
    0xf8, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
static const uint8_t timestretch_operate_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x08, 0x8b, 0x2d, 0xed
};
static const uint8_t timestretch_fgpr_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x02, 0x8b, 0x2d, 0xed
};

/* What the core may call. Everything else here is private to the module. */
static void rx3_keyshift_install(void);
static int rx3_keyshift_ready(void);
static void rx3_keyshift_remove(void);
static void rx3_keyshift_report(void);
static void rx3_keyshift_start_audio(unsigned int sample_rate);
static int rx3_keyshift_semitones(unsigned int deck);
static const uint16_t *rx3_keyshift_label(unsigned int deck);
static void rx3_keyshift_change(unsigned int deck, int delta);
static void rx3_keyshift_reload(unsigned int deck);
static void rx3_keyshift_destroy_deck(unsigned int deck);

#endif /* RX3_KEYSHIFT_DECL_H */
