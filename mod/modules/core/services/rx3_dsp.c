/* SPDX-License-Identifier: MPL-2.0 */
#include "../api/rx3_dsp.h"
static void convert(float *out, const int16_t *in, unsigned int frames)
{
    if (!out || !in) return;
    for (unsigned int i = 0; i < frames; i++) {
        out[0] = (float)in[0] * (1.0f / 32768.0f);
        out[1] = (float)in[1] * (1.0f / 32768.0f);
        out += 2; in += 2;
    }
}
static void gain(float *out, unsigned int frames, struct rx3_gain_ramp *ramp)
{
    if (!out || !ramp) return;
    for (unsigned int i = 0; i < frames; i++) {
        float value = ramp->to;
        if (ramp->cursor < ramp->frames) {
            ramp->cursor++;
            value = ramp->cursor == ramp->frames ? ramp->to :
                rx3_dsp_lerp(ramp->from, ramp->to, (float)ramp->cursor / (float)ramp->frames);
        }
        out[0] *= value; out[1] *= value; out += 2;
    }
}
static void mix(float *out, const float *in, unsigned int frames, float value)
{
    if (!out || !in) return;
    for (unsigned int i = 0; i < frames; i++) {
        out[0] += in[0] * value; out[1] += in[1] * value;
        out += 2; in += 2;
    }
}
static struct rx3_audio_level level(const float *in, unsigned int frames)
{
    struct rx3_audio_level result = {0, 0};
    if (!in || !frames) return result;
    for (unsigned int i = 0; i < frames; i++) {
        for (unsigned int channel = 0; channel < 2; channel++) {
            float sample = in[channel];
            float absolute = sample < 0 ? -sample : sample;
            if (absolute > result.peak) result.peak = absolute;
            result.mean_square += sample * sample;
        }
        in += 2;
    }
    result.mean_square /= (float)frames * 2.0f;
    return result;
}
static uint64_t frames_from_ms(unsigned int ms, unsigned int rate)
{ return (uint64_t)ms * rate / 1000u; }
const struct rx3_dsp_service rx3_dsp = {convert, gain, mix, level, frames_from_ms};
