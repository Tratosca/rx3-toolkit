/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_ECHO_H
#define RX3_STEMS_ECHO_H

#include "rx3_stems_audio.h"

/* Echo out: a pad cuts a role and the beat before the press repeats, each time
   quieter, then silence. Repeating exactly one beat keeps the echo on the grid
   wherever the press lands.

   The stage reads out of order: it re-reads frames and steps back. So nothing
   here counts frames. As in the stems mix, every sample follows from the track
   frame asked for, and a frame read twice gets the same echo twice. */
#define STEMS_ECHO_REPEATS 4u
/* A read further than this from the last one is a jump, not the stage's wander. */
#define STEMS_ECHO_JUMP 8192
static const float stems_echo_levels[STEMS_ECHO_REPEATS] = {0.71f, 0.35f, 0.18f, 0.09f};
/* The deck's mix by track frame: the stems are resident, INST is not. Bss, so
   the module file stays small. Pages are touched by the first track with stems. */
static struct rx3_stereo stems_echo_history[2][STEMS_ECHO_FRAMES];

/* Hundredths of a BPM to frames at 44.1 kHz. No BPM means no echo. */
static unsigned int stems_beat_frames(int bpm)
{
    if (bpm <= 0) return 0u;
    unsigned int frames = 264600000u / (unsigned int)bpm;
    while (frames > STEMS_ECHO_FRAMES) frames /= 2u;
    return frames;
}

/* Input thread. A role already silent has nothing to echo, and a track
   without a BPM falls back to a plain mute: an echo in the wrong tempo is
   worse than none. The level is read before the cut and the request follows
   it, so the audio thread never sees an echo for a role that still plays. A
   role held low by its slider echoes at that level. */
static void stems_echo_out(struct stems_deck_context *context, unsigned int bit,
                           unsigned int frames)
{
    if (!(stems_selected(context) & bit)) return;
    if (frames) {
        __atomic_store_n(&context->echo_frames, frames, __ATOMIC_SEQ_CST);
        __atomic_store_n(&context->echo_level[bit >> 1u], stems_level(context, bit),
                         __ATOMIC_SEQ_CST);
    }
    stems_set_level(context, bit, 0u);
    if (frames) __atomic_fetch_or(&context->echo_request, bit, __ATOMIC_SEQ_CST);
}

/* Audio thread, once per block; returns whether the stage moved on from the
   last block. A jump keeps a ringing echo in time and starts the history again,
   unless INST is repeating from it. A role asked for again while it leaves
   simply stays. */
static int stems_echo_begin(struct stems_deck_context *context, int position,
                            unsigned int block)
{
    int moved = position - context->echo_next;
    int advanced = position + (int)block != context->echo_next;
    context->echo_next = position + (int)block;
    if (moved < -STEMS_ECHO_JUMP || moved > STEMS_ECHO_JUMP) {
        for (unsigned int i = 0; i < 3u; i++) {
            context->echo[i].press += moved;
            context->echo[i].leave += moved;
        }
        if (!context->echo[0].frames) context->echo_valid = 0;
    }
    unsigned int request = __atomic_exchange_n(&context->echo_request, 0u, __ATOMIC_SEQ_CST);
    if (!request) return advanced;
    unsigned int frames = __atomic_load_n(&context->echo_frames, __ATOMIC_SEQ_CST);
    for (unsigned int i = 0; i < 3u; i++) {
        if (!(request & (1u << i))) continue;
        struct stems_echo_tail *tail = &context->echo[i];
        tail->leaving = 0;
        if (tail->frames) continue;
        tail->origin = tail->press = position;
        tail->level = (float)__atomic_load_n(&context->echo_level[i], __ATOMIC_SEQ_CST) * 0.01f;
        __atomic_store_n(&tail->frames, frames, __ATOMIC_SEQ_CST);
    }
    return advanced;
}

/* The block before the mix changes it, in the slots of its track frames. It
   freezes while INST repeats from it. */
static void stems_echo_capture(struct stems_deck_context *context, int position,
                               const struct rx3_stereo *output, unsigned int frames)
{
    if (!context->payload_count || !context->payloads[0].data || context->echo[0].frames) return;
    unsigned int skip = position < 0 ? (unsigned int)-position : 0u;
    if (skip >= frames) return;
    int first = position + (int)skip, last = position + (int)frames;
    if (!context->echo_valid) {
        context->echo_low = context->echo_high = first;
        context->echo_valid = 1;
    }
    struct rx3_stereo *history = stems_echo_history[context == &stems_decks[1]];
    unsigned int slot = (unsigned int)first % STEMS_ECHO_FRAMES;
    for (unsigned int i = skip; i < frames; i++) {
        history[slot] = output[i];
        if (++slot == STEMS_ECHO_FRAMES) slot = 0u;
    }
    if (first < context->echo_low) context->echo_low = first;
    if (last > context->echo_high) context->echo_high = last;
    if (context->echo_high - context->echo_low > (int)STEMS_ECHO_FRAMES)
        context->echo_low = context->echo_high - (int)STEMS_ECHO_FRAMES;
}

/* A role at a track frame. A third payload is legacy bass: it stays inside
   INST, as it does in the mix. */
static struct rx3_stereo stems_echo_read(const struct stems_deck_context *context,
                                         const struct rx3_stereo *history,
                                         unsigned int role, unsigned int frame)
{
    struct rx3_stereo sample = {0.0f, 0.0f};
    if (!role) {
        if (!context->echo_valid || (int)frame < context->echo_low ||
            (int)frame >= context->echo_high) return sample;
        sample = history[frame % STEMS_ECHO_FRAMES];
    }
    unsigned int stored = context->payload_count < 2u ? context->payload_count : 2u;
    for (unsigned int j = 0; j < stored; j++) {
        if (role && role != j + 1u) continue;
        const struct stem_payload *payload = &context->payloads[j];
        const Short2 *pcm = (const Short2 *)payload->data + frame;
        float scale = (payload->format == FORMAT_S16_GAIN ? payload->pcm_gain : 1.0f) *
                      (1.0f / 32768.0f);
        float left = (float)pcm->left * scale, right = (float)pcm->right * scale;
        sample.left += role ? left : -left;
        sample.right += role ? right : -right;
    }
    return sample;
}

/* After the mix, so the repeats add to what the deck plays. A role turned back
   on takes the stage: its echo leaves over one crossfade and capture resumes. */
static void stems_echo_render(struct stems_deck_context *context, int position,
                              struct rx3_stereo *output, unsigned int frames)
{
    unsigned int count = context->payload_count;
    if (!count || count > 3u || !context->payloads[0].data) return;
    uint64_t limit = context->payloads[0].frames;
    for (unsigned int i = 1; i < count; i++)
        if (context->payloads[i].frames < limit) limit = context->payloads[i].frames;
    uint32_t levels = __atomic_load_n(&context->levels, __ATOMIC_SEQ_CST);
    const struct rx3_stereo *history = stems_echo_history[context == &stems_decks[1]];
    int end = position + (int)frames;
    for (unsigned int r = 0; r < 3u; r++) {
        struct stems_echo_tail *tail = &context->echo[r];
        unsigned int beat = tail->frames;
        if (!beat) continue;
        if (!tail->leaving && ((levels >> (r * 7u)) & 127u)) {
            tail->leaving = 1;
            tail->leave = position;
        }
        int offset = position - tail->press;
        unsigned int skip = offset < 0 ? (unsigned int)-offset : 0u;
        if (skip < frames) {
            unsigned int done = (unsigned int)(offset + (int)skip);
            unsigned int repeat = done / beat, at = done - repeat * beat;
            for (unsigned int i = skip; i < frames && repeat < STEMS_ECHO_REPEATS; i++) {
                int source = tail->origin - (int)beat + (int)at;
                if (source >= 0 && (uint64_t)source < limit) {
                    float level = tail->level * stems_echo_levels[repeat] *
                                  rx3_dsp_loop_edge(at, beat);
                    int gone = position + (int)i - tail->leave;
                    if (tail->leaving && gone > 0)
                        level *= gone < (int)TRANSITION_FRAMES ?
                                 (float)((int)TRANSITION_FRAMES - gone) * (1.0f / (float)TRANSITION_FRAMES) : 0.0f;
                    struct rx3_stereo sample =
                        stems_echo_read(context, history, r, (unsigned int)source);
                    output[i].left += sample.left * level;
                    output[i].right += sample.right * level;
                }
                if (++at == beat) {
                    at = 0u;
                    repeat++;
                }
            }
        }
        if (end - tail->press >= (int)(beat * STEMS_ECHO_REPEATS) ||
            (tail->leaving && end - tail->leave >= (int)TRANSITION_FRAMES)) {
            __atomic_store_n(&tail->frames, 0u, __ATOMIC_SEQ_CST);
            if (!r) context->echo_valid = 0;
        }
    }
}

#endif /* RX3_STEMS_ECHO_H */
