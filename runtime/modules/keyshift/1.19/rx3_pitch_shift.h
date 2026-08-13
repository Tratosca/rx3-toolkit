/* SPDX-License-Identifier: MPL-2.0
 *
 * Time-domain pitch shifter for the RX3 performance hook.
 *
 * The firmware's own granular shifter is clean downwards and poor upwards:
 * measured on a 440 Hz tone, -7 semitones leaves 99.9% of the energy on the
 * note while +7 leaves 15.8%, the rest being grain-splice noise. Its grain
 * lengths and crossfade are compiled-in constants, so it cannot be improved
 * from outside. This is the replacement.
 *
 * Two read heads walk a history ring at the pitch ratio, half a grain apart,
 * each windowed by a Hann envelope. Hann at 50% overlap sums to exactly one, so
 * the amplitude is constant and every splice happens where that head's gain is
 * zero. Reads are cubic-interpolated. That is the whole of it: the quality comes
 * from the window satisfying the overlap-add constraint, which is precisely
 * what the stock effect does not do.
 *
 * Self-contained on purpose: no libc, no libm, no allocation. The caller owns
 * the history buffer, so the same code runs inside the LD_PRELOAD hook and in
 * the host measurement harness that produced the figures above.
 */

#ifndef RX3_PITCH_SHIFT_H
#define RX3_PITCH_SHIFT_H

/* Grain length in frames, and it has to depend on the direction.
 *
 * Raising pitch means repeating material: 0.414 s of source per second of
 * output at +6 semitones. The grain decides how that repetition is spread, and
 * a long grain replays whole transients. Measured at +7 semitones against an
 * impulse train of eight hits: 2048 frames returns sixteen -- every hit doubled
 * -- 1024 returns fourteen, 512 returns nine. Below that the shifter falls
 * apart, 256 leaving 0.7% of the energy on the note.
 *
 * Lowering pitch skips material instead of repeating it, so there is no
 * doubling to avoid, and the short grain only costs purity: at -7 semitones,
 * 0.5% of the energy lands on the note with 512 frames against 69% with 2048.
 *
 * Hence one value per direction. */
#define RX3_SHIFT_GRAIN_UP 512u
#define RX3_SHIFT_GRAIN_DOWN 2048u
#define RX3_SHIFT_GRAIN RX3_SHIFT_GRAIN_DOWN
/* Power of two so the ring index is a mask. Must exceed the grain plus the
   cubic interpolator's margin. */
#define RX3_SHIFT_HISTORY 4096u
#define RX3_SHIFT_MASK (RX3_SHIFT_HISTORY - 1u)
/* Hann table resolution. Interpolated between entries, so 1024 is ample. */
#define RX3_SHIFT_TABLE 1024u
/* Per-frame approach of the ratio towards its target: about 11 ms, which keeps
   a key change from stepping the read rate discontinuously. */
#define RX3_SHIFT_GLIDE 0.002f
/* Never read newer than this, so the cubic interpolator's p+1 and p+2 taps stay
   inside written history. */
#define RX3_SHIFT_MARGIN 2.0f

/* Overlapping heads, evenly spaced across the grain.
 *
 * Three heads look better on paper. With Hann windows the amplitude sum is N/2
 * for any N >= 2, and the power sum at N = 2 is 0.5 + 0.5*cos^2, swinging over
 * 3 dB -- the pumping heard whenever the heads cannot be phase-aligned --
 * whereas at N = 3 the doubled angles cancel too and the power sum is a
 * constant 1.125.
 *
 * It was tried and measured, and it fails, because that constant assumes the
 * heads hold fixed relative phases. The correlation alignment gives each head
 * its own offset against a different reference at a different instant, so with
 * three heads their contributions stop summing coherently: purity at +5
 * semitones fell from 99.0% to 0.6%. Constant power is worth nothing if the
 * signal is gone. Two heads it is. */
#define RX3_SHIFT_HEADS 2u
/* Normalise the amplitude sum to unity, which keeps tonal level exact. */
#define RX3_SHIFT_GAIN (2.0f / (float)RX3_SHIFT_HEADS)

/* How far back a restarting head may look for a phase-aligned start. One and a
   half periods of the lowest pitch worth aligning, about 57 Hz at 44.1 kHz. */
#define RX3_SHIFT_ALIGN_MAX 768u
/* Correlation window, and the decimation used for the coarse pass. */
#define RX3_SHIFT_ALIGN_WINDOW 256u
#define RX3_SHIFT_ALIGN_STRIDE 4u

struct rx3_shifter {
    float *history;          /* RX3_SHIFT_HISTORY interleaved stereo frames */
    unsigned long written;   /* frames written since reset */
    float phase;             /* grain phase, [0,1) */
    float ratio;             /* ratio in use */
    float target;            /* ratio asked for */
    float grain;             /* grain length in frames, see RX3_SHIFT_GRAIN */
    /* Per-head start offset, in frames, refreshed when that head restarts.
       Constant across a grain, so the read rate inside a grain stays exactly
       the ratio and the windows still sum flat. */
    float align[RX3_SHIFT_HEADS];
};

/* Equal temperament, -12 to +12. Exact ratios: unlike the stock effect, which
   quantises to integer percentages and lands up to 13 cents off. */
static const float rx3_semitone_ratio[25] = {
    0.500000f, 0.529732f, 0.561231f, 0.594604f, 0.629961f, 0.667420f,
    0.707107f, 0.749154f, 0.793701f, 0.840896f, 0.890899f, 0.943874f,
    1.000000f,
    1.059463f, 1.122462f, 1.189207f, 1.259921f, 1.334840f, 1.414214f,
    1.498307f, 1.587401f, 1.681793f, 1.781797f, 1.887749f, 2.000000f
};

/* Hann, which sums to one in amplitude across a half-grain overlap.
 *
 * A raised sine would sum to one in power instead, and on sustained noise -- 
 * where the correlation alignment cannot make the two heads coherent -- that
 * removes about a decibel of the level ripple. It was measured and rejected:
 * its broader top makes repeated material louder at the splice, and an impulse
 * train of eight hits came back as thirteen at +7 semitones against nine with
 * Hann. Transient doubling is far more audible than a decibel of ripple, so the
 * amplitude-complementary window wins. */
static float rx3_hann_table[RX3_SHIFT_TABLE + 1u];
static int rx3_hann_ready;

/* cos over [-pi, pi] by series. Building a window table is the only place this
   is needed, and it removes any dependency on libm. */
static float rx3_cos(float x)
{
    float square = x * x;
    float term = 1.0f;
    float sum = 1.0f;
    for (unsigned int n = 1; n <= 8u; n++) {
        term *= -square / (float)((2u * n - 1u) * (2u * n));
        sum += term;
    }
    return sum;
}

static void rx3_build_hann(void)
{
    const float two_pi = 6.28318530718f;
    for (unsigned int i = 0; i <= RX3_SHIFT_TABLE; i++) {
        float fraction = (float)i / (float)RX3_SHIFT_TABLE;
        /* Range-reduce to [-pi, pi] before the series. */
        float angle = two_pi * fraction;
        if (angle > 3.14159265359f)
            angle -= two_pi;
        rx3_hann_table[i] = 0.5f - 0.5f * rx3_cos(angle);
    }
    rx3_hann_ready = 1;
}

static float rx3_hann(float fraction)
{
    float scaled = fraction * (float)RX3_SHIFT_TABLE;
    unsigned int index = (unsigned int)scaled;
    if (index >= RX3_SHIFT_TABLE)
        index = RX3_SHIFT_TABLE - 1u;
    float blend = scaled - (float)index;
    return rx3_hann_table[index] +
           (rx3_hann_table[index + 1u] - rx3_hann_table[index]) * blend;
}

/* Catmull-Rom through four neighbours of the fractional read position. */
static float rx3_cubic(float a, float b, float c, float d, float t)
{
    float c0 = b;
    float c1 = 0.5f * (c - a);
    float c2 = a - 2.5f * b + 2.0f * c - 0.5f * d;
    float c3 = 0.5f * (d - a) + 1.5f * (b - c);
    return ((c3 * t + c2) * t + c1) * t + c0;
}

/* Mono value at an integer ring position, for correlation only. */
static float rx3_mono(const float *history, long position)
{
    unsigned int index = (unsigned int)(position & (long)RX3_SHIFT_MASK);
    return history[index * 2u] + history[index * 2u + 1u];
}

/* How far back the restarting head should begin so that its material is in
   phase with the segment currently fading out.
 *
 * Splicing two segments whose phases disagree forces the output phase to slew
 * across the crossfade, and a phase slew per unit time is a frequency error:
 * with a fixed grain that showed up as the whole shift being 97.9% of what was
 * asked, and as the stereo image smearing when the two channels disagreed. The
 * offset is searched coarsely then refined, and only backwards, which keeps the
 * read inside written history. */
static float rx3_align_head(const struct rx3_shifter *state, long outgoing,
                            long incoming)
{
    const float *history = state->history;
    long best_lag = 0;
    float best_score = -1.0e30f;

    for (unsigned int lag = 0; lag < RX3_SHIFT_ALIGN_MAX;
         lag += RX3_SHIFT_ALIGN_STRIDE) {
        float score = 0.0f;
        for (unsigned int i = 0; i < RX3_SHIFT_ALIGN_WINDOW;
             i += RX3_SHIFT_ALIGN_STRIDE)
            score += rx3_mono(history, outgoing + (long)i) *
                     rx3_mono(history, incoming - (long)lag + (long)i);
        if (score > best_score) {
            best_score = score;
            best_lag = (long)lag;
        }
    }
    if (best_score <= 0.0f)
        return 0.0f;   /* nothing to align to: leave the nominal start alone */

    long low = best_lag - (long)RX3_SHIFT_ALIGN_STRIDE;
    long high = best_lag + (long)RX3_SHIFT_ALIGN_STRIDE;
    if (low < 0)
        low = 0;
    if (high > (long)RX3_SHIFT_ALIGN_MAX)
        high = (long)RX3_SHIFT_ALIGN_MAX;
    float fine_score = -1.0e30f;
    long fine_lag = best_lag;
    for (long lag = low; lag <= high; lag++) {
        float score = 0.0f;
        for (unsigned int i = 0; i < RX3_SHIFT_ALIGN_WINDOW; i++)
            score += rx3_mono(history, outgoing + (long)i) *
                     rx3_mono(history, incoming - lag + (long)i);
        if (score > fine_score) {
            fine_score = score;
            fine_lag = lag;
        }
    }

    return (float)fine_lag;
}

static void rx3_shifter_init(struct rx3_shifter *state, float *history)
{
    if (!rx3_hann_ready)
        rx3_build_hann();
    state->history = history;
    state->written = 0;
    state->phase = 0.0f;
    state->ratio = 1.0f;
    state->target = 1.0f;
    for (unsigned int head = 0; head < RX3_SHIFT_HEADS; head++)
        state->align[head] = 0.0f;
    state->grain = (float)RX3_SHIFT_GRAIN;
    for (unsigned int i = 0; i < RX3_SHIFT_HISTORY * 2u; i++)
        history[i] = 0.0f;
}

static void rx3_shifter_set_semitones(struct rx3_shifter *state, int semitones)
{
    if (semitones < -12)
        semitones = -12;
    if (semitones > 12)
        semitones = 12;
    state->target = rx3_semitone_ratio[semitones + 12];
    state->grain = state->target > 1.0f ? (float)RX3_SHIFT_GRAIN_UP
                                        : (float)RX3_SHIFT_GRAIN_DOWN;
}

/* True while the shifter still has work to do: the caller may skip it once the
   ratio has settled back to unity, but must keep feeding history. */
static int rx3_shifter_is_active(const struct rx3_shifter *state)
{
    float error = state->ratio - 1.0f;
    if (error < 0.0f)
        error = -error;
    return state->target != 1.0f || error > 0.0001f;
}

/* Fill history without shifting, for the bypassed case. Keeping the ring warm
   is what lets a later key change start from real audio instead of silence. */
static void rx3_shifter_absorb(struct rx3_shifter *state, const float *io,
                               unsigned int frames)
{
    for (unsigned int i = 0; i < frames; i++) {
        unsigned int slot = (unsigned int)(state->written & RX3_SHIFT_MASK);
        state->history[slot * 2u] = io[i * 2u];
        state->history[slot * 2u + 1u] = io[i * 2u + 1u];
        state->written++;
    }
    state->phase = 0.0f;
    state->ratio = state->target;
    for (unsigned int head = 0; head < RX3_SHIFT_HEADS; head++)
        state->align[head] = 0.0f;
}

static void rx3_shifter_process(struct rx3_shifter *state, float *io,
                                unsigned int frames)
{
    const float grain = state->grain;
    float *history = state->history;

    for (unsigned int i = 0; i < frames; i++) {
        unsigned int slot = (unsigned int)(state->written & RX3_SHIFT_MASK);
        history[slot * 2u] = io[i * 2u];
        history[slot * 2u + 1u] = io[i * 2u + 1u];
        state->written++;

        float left = 0.0f;
        float right = 0.0f;
        for (unsigned int head = 0; head < RX3_SHIFT_HEADS; head++) {
            float fraction = state->phase +
                             (float)head / (float)RX3_SHIFT_HEADS;
            while (fraction >= 1.0f)
                fraction -= 1.0f;
            float delay = RX3_SHIFT_MARGIN + fraction * grain +
                          state->align[head];
            /* Split the read position into an exact integer part and a small
               fraction. Forming it as a single float would round the fraction
               away: the frame counter reaches six figures within seconds, where
               a float32 step is already a fraction of a sample, and that
               fraction is the whole of the pitch shift. */
            unsigned long whole = (unsigned long)delay;
            float remainder = delay - (float)whole;
            long base = (long)(state->written - 2u - whole);
            float t = 1.0f - remainder;
            float window = rx3_hann(fraction);
            for (unsigned int channel = 0; channel < 2u; channel++) {
                unsigned int i0 = (unsigned int)((base - 1) & (long)RX3_SHIFT_MASK);
                unsigned int i1 = (unsigned int)(base & (long)RX3_SHIFT_MASK);
                unsigned int i2 = (unsigned int)((base + 1) & (long)RX3_SHIFT_MASK);
                unsigned int i3 = (unsigned int)((base + 2) & (long)RX3_SHIFT_MASK);
                float value = rx3_cubic(history[i0 * 2u + channel],
                                        history[i1 * 2u + channel],
                                        history[i2 * 2u + channel],
                                        history[i3 * 2u + channel], t);
                if (channel == 0u)
                    left += window * value;
                else
                    right += window * value;
            }
        }
        io[i * 2u] = left * RX3_SHIFT_GAIN;
        io[i * 2u + 1u] = right * RX3_SHIFT_GAIN;

        /* The delay between write and read changes at 1 - ratio per frame, and
           the phase is that delay expressed in grains. */
        float previous_phase = state->phase;
        state->phase += (1.0f - state->ratio) / grain;
        while (state->phase >= 1.0f)
            state->phase -= 1.0f;
        while (state->phase < 0.0f)
            state->phase += 1.0f;
        /* A head restarts when its own fraction crosses zero: head 0 at the
           grain boundary, head 1 half a grain later. Realign it there, while
           its window is at zero and the splice is inaudible. */
        for (unsigned int head = 0; head < RX3_SHIFT_HEADS; head++) {
            float offset = (float)head / (float)RX3_SHIFT_HEADS;
            float before = previous_phase + offset;
            float after = state->phase + offset;
            while (before >= 1.0f)
                before -= 1.0f;
            while (after >= 1.0f)
                after -= 1.0f;
            int restarted = state->ratio > 1.0f ? after > before : after < before;
            if (!restarted)
                continue;
            /* Align to whichever other head is nearest the middle of its own
               window, since that is the one carrying the sound right now. */
            unsigned int other = head;
            float best_weight = -1.0f;
            for (unsigned int candidate = 0; candidate < RX3_SHIFT_HEADS;
                 candidate++) {
                if (candidate == head)
                    continue;
                float f = state->phase +
                          (float)candidate / (float)RX3_SHIFT_HEADS;
                while (f >= 1.0f)
                    f -= 1.0f;
                float weight = rx3_hann(f);
                if (weight > best_weight) {
                    best_weight = weight;
                    other = candidate;
                }
            }
            float other_fraction = state->phase +
                                   (float)other / (float)RX3_SHIFT_HEADS;
            while (other_fraction >= 1.0f)
                other_fraction -= 1.0f;
            long outgoing = (long)(state->written - 2u) -
                            (long)(RX3_SHIFT_MARGIN + other_fraction * grain +
                                   state->align[other]);
            long incoming = (long)(state->written - 2u) -
                            (long)(RX3_SHIFT_MARGIN + after * grain);
            state->align[head] = rx3_align_head(state, outgoing, incoming);
        }
        state->ratio += (state->target - state->ratio) * RX3_SHIFT_GLIDE;
    }
}

#endif /* RX3_PITCH_SHIFT_H */
