/* SPDX-License-Identifier: MPL-2.0 */
/* BEAT FX frequency bands, after the FX FREQUENCY buttons of Pioneer's
 * DJM-900NXS2, A9 and V10: SPACE, DUB ECHO and SWEEP become LOW, MID and HIGH.
 * A lit button sends its band through BEAT FX; a dark one keeps that band dry,
 * around the effect. All three lit is the stock effect, sample for sample.
 *
 * The bands are the player's own isolator crossover (rbp 1.19
 * IsolatorCoeffs_AllinOne, see REFERENCES.md): Pioneer does not publish the
 * DJM's FX FREQUENCY split, and this is Pioneer's split on this platform. */
#include "../core/api/rx3_module_api.h"

static const char owner[] = "beatfx-eq";
static const struct rx3_input_service *input;
static const struct rx3_audio_service *audio;

#define BAND_LOW  1u
#define BAND_MID  2u
#define BAND_HIGH 4u
#define BAND_ALL  7u
/* Bands sent to BEAT FX; written by the input thread, read once per block. */
static unsigned int bands = BAND_ALL;

/* (b0, b1, b2, a1, a2), denominator 1 + a1 z^-1 + a2 z^-2, the stored binary32
   values: high-pass and low-pass at about 4649 Hz and 284 Hz, Q 0.7071068.
   Each is run twice, a fourth-order (24 dB/octave) edge. */
static const float hp_upper[5] = {0.623243510723114f, -1.246487021446228f, 0.623243510723114f,
                                  -1.0991116762161255f, 0.3938623368740082f};
static const float hp_lower[5] = {0.9717935919761658f, -1.9435871839523315f, 0.9717935919761658f,
                                  -1.94279146194458f, 0.9443829655647278f};
static const float lp_upper[5] = {0.07368765771389008f, 0.14737531542778015f, 0.07368765771389008f,
                                  -1.0991116762161255f, 0.3938623368740082f};
static const float lp_lower[5] = {0.0003978797176387161f, 0.0007957594352774322f,
                                  0.0003978797176387161f, -1.94279146194458f, 0.9443829655647278f};

/* The isolator's own gain ramp, SMOOTHING_TIME 3.3 ms in whole frames. */
#define RAMP_FRAMES 145.0f

struct section { float x1, x2, y1, y2; };
/* One crossover per stream: LOW 2, MID 4, HIGH 2 sections, per channel. */
struct path {
    struct section low[2][2], mid[4][2], high[2][2];
    float gain[3]; /* 1 sends the band to the effect, 0 keeps it dry */
    float split;   /* 0 is the untouched block, 1 the band split */
};
/* Audio thread only. The effect and the Roll pre-capture are two streams. */
static struct path effect_path, capture_path;
static struct rx3_stereo dry[RX3_BEAT_FX_CAPTURE_FRAMES];
static unsigned int dry_frames;

static float run(struct section *s, const float c[5], float x)
{
    float y = c[0] * x + c[1] * s->x1 + c[2] * s->x2 - c[3] * s->y1 - c[4] * s->y2;
    s->x2 = s->x1; s->x1 = x; s->y2 = s->y1; s->y1 = y;
    return y;
}

static float toward(float value, float target)
{
    const float step = 1.0f / RAMP_FRAMES;
    if (value < target) return value + step < target ? value + step : target;
    return value - step > target ? value - step : target;
}

/* block becomes what the effect receives; keep, when given, what stays dry. */
static void split(struct path *p, struct rx3_stereo *block, struct rx3_stereo *keep,
                  unsigned int frames)
{
    unsigned int mask = __atomic_load_n(&bands, __ATOMIC_SEQ_CST);
    float target_split = mask == BAND_ALL ? 0.0f : 1.0f;
    for (unsigned int i = 0; i < frames; i++) {
        for (unsigned int b = 0; b < 3u; b++)
            p->gain[b] = toward(p->gain[b], (mask >> b) & 1u ? 1.0f : 0.0f);
        p->split = toward(p->split, target_split);
        float *sample[2] = {&block[i].left, &block[i].right};
        float kept[2];
        for (unsigned int c = 0; c < 2u; c++) {
            float x = *sample[c];
            float low = run(&p->low[1][c], lp_lower, run(&p->low[0][c], lp_lower, x));
            float mid = run(&p->mid[1][c], hp_lower, run(&p->mid[0][c], hp_lower, x));
            mid = run(&p->mid[3][c], lp_upper, run(&p->mid[2][c], lp_upper, mid));
            float high = run(&p->high[1][c], hp_upper, run(&p->high[0][c], hp_upper, x));
            float sent = p->gain[0] * low + p->gain[1] * mid + p->gain[2] * high;
            kept[c] = p->split * ((low + mid + high) - sent);
            *sample[c] = x + p->split * (sent - x);
        }
        if (keep) { keep[i].left = kept[0]; keep[i].right = kept[1]; }
    }
}

static void capture(struct rx3_stereo *block, unsigned int frames)
{
    split(&capture_path, block, 0, frames);
}

static void send(struct rx3_stereo *block, unsigned int frames)
{
    /* shortcut: a block longer than the dry buffer passes unsplit; native
       blocks are far shorter, recheck if the player's buffer size changes. */
    if (frames > RX3_BEAT_FX_CAPTURE_FRAMES) { dry_frames = 0; return; }
    split(&effect_path, block, dry, frames);
    dry_frames = frames;
}

static void ret(struct rx3_stereo *block, unsigned int frames)
{
    if (frames != dry_frames) return;
    for (unsigned int i = 0; i < frames; i++) {
        block[i].left += dry[i].left;
        block[i].right += dry[i].right;
    }
}

static const struct rx3_beat_fx_client client = {capture, send, ret};

/* Each press arrives once per mixer channel, 1 then 2: channel 1 toggles,
   and every copy is consumed so the native COLOR FX never sees these keys. */
static int on_key(const struct rx3_key_event *e)
{
    unsigned int band = e->key == RX3_KEY_COLOR_FX_SPACE ? 0u :
                        e->key == RX3_KEY_COLOR_FX_DUB_ECHO ? 1u :
                        e->key == RX3_KEY_COLOR_FX_SWEEP ? 2u : 3u;
    if (band > 2u) return 0;
    if (e->operation == 0u && e->channel == 1u) __atomic_fetch_xor(&bands, 1u << band, __ATOMIC_SEQ_CST);
    return 1;
}

/* RX3_LIGHT_COLOR_FX_SPACE, DUB_ECHO and SWEEP are 0, 1 and 2: the band bits. */
static void light(unsigned int deck, unsigned int control, struct rx3_light *state)
{
    (void)deck;
    if (control > RX3_LIGHT_COLOR_FX_SWEEP) return;
    state->state = (__atomic_load_n(&bands, __ATOMIC_SEQ_CST) >> control) & 1u ? RX3_LIGHT_ON
                                                                                : RX3_LIGHT_OFF;
}

static int configured(void)
{
    const char *value = getenv("RX3_BEATFX_EQ");
    return value && value[0] == '1' && !value[1];
}

static void stop(void)
{
    if (audio) audio->release_beat_fx(owner);
    if (input) input->unregister_owner(owner);
    audio = 0; input = 0;
}

static int start(const struct rx3_services *services)
{
    input = services->input; audio = services->audio;
    if (!input || !audio) return 0;
    __atomic_store_n(&bands, BAND_ALL, __ATOMIC_SEQ_CST);
    memset(&effect_path, 0, sizeof(effect_path));
    memset(&capture_path, 0, sizeof(capture_path));
    for (unsigned int b = 0; b < 3u; b++) effect_path.gain[b] = capture_path.gain[b] = 1.0f;
    dry_frames = 0;
    if (input->register_key(owner, 10u, on_key) &&
        input->register_lights(owner, RX3_LIGHTS_MIXER, light) &&
        audio->claim_beat_fx(owner, &client)) return 1;
    stop();
    return 0;
}

const struct rx3_module rx3_beatfx_eq_module = {
    RX3_MODULE_API_VERSION, sizeof(struct rx3_module), owner, configured, start, stop,
    0, 0, 0, 0, 0, 0
};
