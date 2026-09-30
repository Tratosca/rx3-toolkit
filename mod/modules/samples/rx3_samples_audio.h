/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_SAMPLES_AUDIO_H
#define RX3_SAMPLES_AUDIO_H
#include "../core/api/rx3_dsp.h"
#include "../core/api/rx3_audio_api.h"

static uint32_t samples_le32(const uint8_t *bytes)
{
    return bytes[0] | ((uint32_t)bytes[1] << 8u) |
        ((uint32_t)bytes[2] << 16u) | ((uint32_t)bytes[3] << 24u);
}

static unsigned int samples_le16(const uint8_t *bytes)
{
    return bytes[0] | ((unsigned int)bytes[1] << 8u);
}

/* Accept one fmt and one data chunk, in either order. Unknown chunks still
   need their declared size and odd-byte padding to fit inside the RIFF. */
static const uint8_t *samples_wave_data(const uint8_t *wave, size_t size,
                                       unsigned int *bytes)
{
    *bytes = 0u;
    if (!wave || size < 12u || size > SAMPLES_BANK_MAX_BYTES ||
        memcmp(wave, "RIFF", 4u) || memcmp(wave + 8u, "WAVE", 4u))
        return 0;
    uint32_t riff = samples_le32(wave + 4u);
    if (riff < 4u || riff > size - 8u)
        return 0;
    size_t end = riff + 8u;
    size_t cursor = 12u;
    const uint8_t *format = 0;
    const uint8_t *data = 0;
    unsigned int length = 0u;
    while (end - cursor >= 8u) {
        const uint8_t *chunk = wave + cursor;
        uint32_t count = samples_le32(chunk + 4u);
        cursor += 8u;
        if (count > end - cursor)
            return 0;
        if (!memcmp(chunk, "fmt ", 4u)) {
            if (format || count < 16u)
                return 0;
            format = wave + cursor;
        } else if (!memcmp(chunk, "data", 4u)) {
            if (data)
                return 0;
            data = wave + cursor;
            length = count;
        }
        cursor += count;
        if (count & 1u) {
            if (cursor == end)
                return 0;
            cursor++;
        }
    }
    if (cursor != end || !format || !data ||
        samples_le16(format) != 1u || samples_le16(format + 2u) != 2u ||
        samples_le32(format + 4u) != SAMPLES_RATE ||
        samples_le32(format + 8u) != SAMPLES_RATE * SAMPLES_FRAME_BYTES ||
        samples_le16(format + 12u) != SAMPLES_FRAME_BYTES ||
        samples_le16(format + 14u) != 16u ||
        length < SAMPLES_FRAME_BYTES || length % SAMPLES_FRAME_BYTES)
        return 0;
    *bytes = length > SAMPLES_MAX_FRAMES * SAMPLES_FRAME_BYTES
        ? SAMPLES_MAX_FRAMES * SAMPLES_FRAME_BYTES : length;
    return data;
}

/* The master buffer already contains the player. Add samples before its
   talkover attenuator runs, with the same squared volume and PCM16 scaling. */
static void samples_mix(struct sample_slot voices[SAMPLES_PAD_COUNT],
                         struct rx3_stereo *output, int frames, unsigned int volume)
{
    if (!output || frames <= 0)
        return;
    if (volume > SAMPLES_VOLUME_MAX)
        volume = SAMPLES_VOLUME_MAX;
    float gain = (float)volume * 0.01f;
    gain = gain * gain * 0.5f * (1.0f / 32768.0f);
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) {
        struct sample_slot *voice = &voices[pad];
        unsigned int state = __atomic_load_n(&voice->position, __ATOMIC_SEQ_CST);
        unsigned int position = state & SAMPLE_CURSOR_MASK;
        const int16_t *data = voice->frames;
        unsigned int length = voice->length;
        if (position == SAMPLE_CURSOR_MASK || !data || !length)
            continue;
        unsigned int mode = __atomic_load_n(&voice->mode, __ATOMIC_SEQ_CST);
        /* The pad's own trim, on top of the bank's volume. Read from the voice
           rather than the config so a bank reloaded mid-sound cannot step the
           level of something already playing. */
        unsigned int trim = __atomic_load_n(&voice->gain, __ATOMIC_SEQ_CST);
        if (trim > SAMPLES_GAIN_MAX) trim = SAMPLES_GAIN_MAX;
        float level = gain * (float)trim * 0.01f;
        /* A loop fills the whole block. Clamping it to what is left would
           leave a gap of up to one block after every wrap, which is audible on
           a short sound and is the whole point of the mode. */
        unsigned int count = (unsigned int)frames;
        if (mode != SAMPLE_MODE_LOOP) {
            count = position < length ? length - position : 0u;
            if (count > (unsigned int)frames)
                count = (unsigned int)frames;
        }
        /* A running index rather than a modulo: this arm has no hardware
           integer divide, and a modulo here is one division per frame per pad. */
        unsigned int at = position;
        for (unsigned int i = 0; i < count; i++) {
            /* A 32-frame edge ramp reduces the discontinuity at a loop's
               splice. Very short buffers stay unshaped; one-shots are intact. */
            float edge = mode == SAMPLE_MODE_LOOP ? rx3_dsp_loop_edge(at, length) : 1.0f;
            output[i].left += (float)data[at * 2u] * level * edge;
            output[i].right += (float)data[at * 2u + 1u] * level * edge;
            if (++at >= length)
                at = 0u;
        }
        unsigned int next = mode == SAMPLE_MODE_LOOP ? at
            : (position + count >= length ? SAMPLE_SLOT_IDLE : position + count);
        /* A command changes the generation even when its cursor is unchanged. */
        next = (state & ~SAMPLE_CURSOR_MASK) | (next & SAMPLE_CURSOR_MASK);
        __sync_bool_compare_and_swap(&voice->position, state, next);
    }
}

#endif /* RX3_SAMPLES_AUDIO_H */
