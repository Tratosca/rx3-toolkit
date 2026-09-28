/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_DSP_H
#define RX3_DSP_H
#include "rx3_platform.h"
/* Scalar kernels can be inlined in an existing sample loop. No allocation,
 * I/O, hidden state, normalization or clipping. Caller owns all buffers.
 */
static inline float rx3_dsp_lerp(float from, float to, float alpha)
{ return from + (to - from) * alpha; }
static inline float rx3_dsp_loop_edge(unsigned int at, unsigned int length)
{
    if (length < 128u) return 1.0f;
    if (at < 32u) return (float)(at + 1u) * (1.0f / 32.0f);
    if (at >= length - 32u) return (float)(length - at) * (1.0f / 32.0f);
    return 1.0f;
}
struct rx3_gain_ramp { float from, to; unsigned int cursor, frames; };
struct rx3_audio_level { float peak, mean_square; };
/* counts below are interleaved stereo FRAMES, not individual samples.
 * PCM16 uses 1/32768. Gain ramp advances once per frame; first frame takes
 * step 1, last frame reaches target. Zero frames means immediate target.
 * mix permits exact src==dst, but not partial overlap. convert requires
 * disjoint buffers. Non-finite samples propagate through processing.
 */
struct rx3_dsp_service {
    void (*pcm16_to_float)(float *, const int16_t *, unsigned int frames);
    void (*gain)(float *, unsigned int frames, struct rx3_gain_ramp *);
    void (*mix)(float *, const float *, unsigned int frames, float gain);
    struct rx3_audio_level (*level)(const float *, unsigned int frames);
    uint64_t (*frames_from_ms)(unsigned int ms, unsigned int sample_rate);
};
extern const struct rx3_dsp_service rx3_dsp;
#endif
