/* SPDX-License-Identifier: MPL-2.0 */
/* Typed audio stages and the deck identity they are resolved against. The
 * callbacks run on the player's audio threads: this file adds no allocation,
 * I/O or waiting to those paths. Claims and releases run serially. */
#include "../api/rx3_audio_api.h"
#include "rx3_audio.h"
#include "rx3_hooks.h"
#include "rx3_log.h"

/* dsp::TimeStretch::getStreamAt is the deck's playback stream: it wraps
   PcmReader::getStreamAt and is the speed and master-tempo stage, so its
   output is what the deck plays. PcmReader::getStreamAt itself is shared with
   the BPM and waveform scan, which walks a track out of order; a sequential
   process cannot sit there. TimeStretch+4 is the reader, which names the deck. */
#define TIMESTRETCH_STREAM ((unsigned long)0x000c292c)
static const uint8_t stream_guard[8] = {0xf8,0x40,0x2d,0xe9,0x00,0x40,0xa0,0xe1};
/* The master bus, just before the microphone talkover attenuator. */
#define MIC_TALKOVER ((unsigned long)0x0009c750)
static const uint8_t master_guard[8] = {0x03,0xc0,0xd0,0xe5,0x04,0x40,0x2d,0xe5};

/* mixerengine::BeatEffectManager, called on the bus BEAT FX is assigned to:
   copyMusicData (the Roll pre-capture, const input) then operateBeatEffect
   (in place; its bool is the native effect position test, passed through). */
#define BEAT_FX_OPERATE ((unsigned long)0x0008a52c)
static const uint8_t beat_fx_operate_guard[8] = {0xf8,0x45,0x2d,0xe9,0x01,0x60,0xa0,0xe1};
#define BEAT_FX_CAPTURE ((unsigned long)0x0008af50)
static const uint8_t beat_fx_capture_guard[8] = {0x70,0x40,0x2d,0xe9,0x00,0x40,0xa0,0xe1};

typedef unsigned long (*stream_fn)(void *, unsigned long, struct rx3_stereo *, unsigned long);
typedef void (*talkover_fn)(void *, void *, struct rx3_stereo *, int);
typedef void (*operate_fn)(void *, struct rx3_stereo *, int, int);
typedef void (*capture_fn)(void *, const struct rx3_stereo *, int);

struct stage {
    struct installed_hook hook;
    void *original;
    const void *owner;
    void *client;
    unsigned int active;
};
static struct stage deck_stage, master_stage, beat_fx_stage, capture_stage;
/* Audio thread only: the pre-capture runs once per block on one bus. */
static struct rx3_stereo capture_copy[RX3_BEAT_FX_CAPTURE_FRAMES];
static void *volatile deck_readers[2];

static void drain(struct stage *stage)
{
    for (;;) {
        while (__atomic_load_n(&stage->active, __ATOMIC_SEQ_CST)) usleep(1000u);
        usleep(10000u);
        if (!__atomic_load_n(&stage->active, __ATOMIC_SEQ_CST)) return;
    }
}

static unsigned long stream_hooked(void *stretch, unsigned long position,
                                   struct rx3_stereo *output, unsigned long frames)
{
    __atomic_add_fetch(&deck_stage.active, 1u, __ATOMIC_SEQ_CST);
    unsigned long result = ((stream_fn)deck_stage.original)(stretch, position, output, frames);
    rx3_deck_stream_fn client = __atomic_load_n(&deck_stage.client, __ATOMIC_SEQ_CST);
    const void *reader = *(void **)((uint8_t *)stretch + 4u);
    int deck = rx3_audio_deck_for_reader(reader);
    if (client && output && frames && deck >= 0)
        client((unsigned int)deck, reader, (int)position, output, (unsigned int)frames);
    __atomic_sub_fetch(&deck_stage.active, 1u, __ATOMIC_SEQ_CST);
    return result;
}

static void master_hooked(void *self, void *state, struct rx3_stereo *output, int frames)
{
    __atomic_add_fetch(&master_stage.active, 1u, __ATOMIC_SEQ_CST);
    rx3_master_fn client = __atomic_load_n(&master_stage.client, __ATOMIC_SEQ_CST);
    if (client && output && frames > 0) client(output, (unsigned int)frames);
    ((talkover_fn)master_stage.original)(self, state, output, frames);
    __atomic_sub_fetch(&master_stage.active, 1u, __ATOMIC_SEQ_CST);
}

static void beat_fx_hooked(void *manager, struct rx3_stereo *block, int frames, int position)
{
    __atomic_add_fetch(&beat_fx_stage.active, 1u, __ATOMIC_SEQ_CST);
    const struct rx3_beat_fx_client *client = __atomic_load_n(&beat_fx_stage.client, __ATOMIC_SEQ_CST);
    if (client && block && frames > 0) client->send(block, (unsigned int)frames);
    ((operate_fn)beat_fx_stage.original)(manager, block, frames, position);
    if (client && block && frames > 0) client->ret(block, (unsigned int)frames);
    __atomic_sub_fetch(&beat_fx_stage.active, 1u, __ATOMIC_SEQ_CST);
}

static void capture_hooked(void *manager, const struct rx3_stereo *block, int frames)
{
    __atomic_add_fetch(&capture_stage.active, 1u, __ATOMIC_SEQ_CST);
    const struct rx3_beat_fx_client *client = __atomic_load_n(&capture_stage.client, __ATOMIC_SEQ_CST);
    if (client && block && frames > 0 && (unsigned int)frames <= RX3_BEAT_FX_CAPTURE_FRAMES) {
        memcpy(capture_copy, block, (unsigned int)frames * sizeof(capture_copy[0]));
        client->capture(capture_copy, (unsigned int)frames);
        block = capture_copy;
    }
    ((capture_fn)capture_stage.original)(manager, block, frames);
    __atomic_sub_fetch(&capture_stage.active, 1u, __ATOMIC_SEQ_CST);
}

static int claim(struct stage *stage, const void *owner, void *client, unsigned long address,
                 const uint8_t guard[8], void *replacement)
{
    if (!owner || !client || stage->owner) return 0;
    if (!stage->original) {
        stage->original = install_hook(&stage->hook, address, guard, replacement, (void **)&stage->original);
        if (!stage->original) return 0;
    }
    stage->owner = owner;
    __atomic_store_n(&stage->client, client, __ATOMIC_SEQ_CST);
    return 1;
}

/* Detach first, then drain, then release the trampoline. A failed restore
   keeps the replacement reachable, passing audio through untouched. */
static void release(struct stage *stage, const void *owner)
{
    if (!owner || stage->owner != owner) return;
    __atomic_store_n(&stage->client, 0, __ATOMIC_SEQ_CST);
    int detached = stage->original && detach_hook(&stage->hook);
    drain(stage);
    stage->owner = 0;
    if (!stage->original) return;
    if (!detached) {
        log_line("audio: native stage retained after restore failure");
        return;
    }
    (void)release_hook(&stage->hook);
    stage->original = 0;
}

static int claim_deck_stream(const void *owner, rx3_deck_stream_fn client)
{
    return claim(&deck_stage, owner, (void *)client, TIMESTRETCH_STREAM, stream_guard,
                 (void *)stream_hooked);
}
static void release_deck_stream(const void *owner) { release(&deck_stage, owner); }
static int claim_master(const void *owner, rx3_master_fn client)
{
    return claim(&master_stage, owner, (void *)client, MIC_TALKOVER, master_guard,
                 (void *)master_hooked);
}
static void release_master(const void *owner) { release(&master_stage, owner); }
/* One owner for both hooks: the capture and the effect must see the same
   client, or Roll would replay a band the effect no longer receives. */
static int claim_beat_fx(const void *owner, const struct rx3_beat_fx_client *client)
{
    if (!client || !client->capture || !client->send || !client->ret) return 0;
    if (!claim(&capture_stage, owner, (void *)client, BEAT_FX_CAPTURE, beat_fx_capture_guard,
               (void *)capture_hooked)) return 0;
    if (claim(&beat_fx_stage, owner, (void *)client, BEAT_FX_OPERATE, beat_fx_operate_guard,
              (void *)beat_fx_hooked)) return 1;
    release(&capture_stage, owner);
    return 0;
}
static void release_beat_fx(const void *owner)
{
    release(&beat_fx_stage, owner);
    release(&capture_stage, owner);
}

/* PcmReader::load runs on the native loading thread. The old reader stops
   naming a deck before the load; the new one only after it. */
void rx3_audio_track_loading(unsigned int deck)
{
    if (deck < 2u) __atomic_store_n(&deck_readers[deck], 0, __ATOMIC_SEQ_CST);
}
void rx3_audio_track_loaded(unsigned int deck, void *reader)
{
    if (deck < 2u) __atomic_store_n(&deck_readers[deck], reader, __ATOMIC_SEQ_CST);
}
int rx3_audio_deck_for_reader(const void *reader)
{
    for (unsigned int deck = 0; deck < 2u; deck++)
        if (reader && __atomic_load_n(&deck_readers[deck], __ATOMIC_SEQ_CST) == reader)
            return (int)deck;
    return -1;
}
unsigned int rx3_audio_count(void)
{
    return (deck_stage.owner != 0) + (master_stage.owner != 0) + (beat_fx_stage.owner != 0);
}

const struct rx3_audio_service rx3_audio = {
    claim_deck_stream, release_deck_stream, claim_master, release_master,
    claim_beat_fx, release_beat_fx
};
