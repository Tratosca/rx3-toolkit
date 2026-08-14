/* SPDX-License-Identifier: MPL-2.0
 *
 * Key shift for the RX3 performance runtime: implementation.
 *
 * Included by the core hook after its logging, hook installer and deck table
 * are in place. Nothing in the core implements key shift; it only calls
 * rx3_keyshift_install, rx3_keyshift_remove, and the accessors the KEY panel
 * needs.
 *
 * The pitch stage sits on dsp::TimeStretchScratch::operate and its Master Tempo
 * counterpart, which are the deck's playback blocks. It deliberately does not
 * sit on PcmReader::getStreamAt: that is a random-access read shared with the
 * BPM and waveform analysis scan, and measurement on hardware found only 13.6%
 * of its calls continuing the previous one.
 */

#ifndef RX3_KEYSHIFT_H
#define RX3_KEYSHIFT_H

static volatile unsigned long pitch_execute_calls[2];
static volatile unsigned long pitch_last_frames[2];
/* Diagnostic only. The pitch DSP carries a sequential grain cursor, so it is
   only correct if getStreamAt walks each deck forward one block at a time.
   These counters say whether it does, and whether one block fits its budget. */
static volatile unsigned long stream_calls[2];
static volatile unsigned long pitch_us_max[2];
static volatile unsigned long pitch_us_last[2];
static volatile unsigned long pitch_budget_us[2];
static volatile unsigned long pitch_over_budget[2];
static volatile unsigned long linear_observed_frames;
static volatile unsigned long pitch_in_peak[2];
static volatile unsigned long pitch_out_peak[2];
static volatile unsigned long pitch_state_ratio[2];
static volatile unsigned long pitch_state_engaged[2];
static volatile unsigned long operate_calls;
static volatile unsigned long operate_frames;
static uint32_t pitch_block_size = PITCH_MAX_FRAMES;
static uint32_t pitch_sample_rate = 44100u;

/* At level/depth 0.5 the effect's shift speed is exactly percent/100, so its
   -50 .. +100 percentage range covers precisely -12 .. +12 semitones. The
   percentages are the closest ones the stock integer quantiser can express;
   tools/rx3_firmware/emulate_pitch.py derives and measures them against the
   real DSP. The worst case is -9 semitones, 13 cents flat. */
static const signed char semitone_percent[25] = {
    -50, -47, -44, -41, -37, -33, -29, -25, -21, -16, -11, -6, 0,
    6, 12, 19, 26, 33, 41, 50, 59, 68, 78, 89, 100
};

/* adjustParameter converts with a truncating vcvt, so bias the request by half
   a percent to land on the intended integer in both directions. */
static float percent_request(int semitones)
{
    int percent = semitone_percent[semitones + 12];
    return (float)percent + (percent >= 0 ? 0.5f : -0.5f);
}

static void publish_pitch_percent(void *object, int semitones)
{
    ((pitch_adjust_fn)PITCH_ADJUST_PARAMETER)(object, PITCH_PARAM_PERCENT,
                                              percent_request(semitones));
}

static void destroy_pitch(struct rx3_keyshift_deck *context)
{
    if (context->pitch) {
        ((pitch_dtor_fn)PITCH_DTOR)(context->pitch);
        munmap(context->pitch, 4096u);
    }
    if (context->pitch_output)
        munmap(context->pitch_output, PITCH_MAX_FRAMES * sizeof(Float2));
    context->pitch = 0;
    context->pitch_output = 0;
}

static int create_pitch(struct rx3_keyshift_deck *context)
{
    void *object = mmap(0, 4096u, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (object == MAP_FAILED)
        return -1;
    Float2 *output = mmap(0, PITCH_MAX_FRAMES * sizeof(Float2),
                          PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (output == MAP_FAILED) {
        munmap(object, 4096u);
        return -1;
    }
    ((pitch_ctor_fn)PITCH_CTOR)(object);
    *(uint32_t *)((uint8_t *)object + 4u) = pitch_sample_rate;
    *(uint32_t *)((uint8_t *)object + 8u) = pitch_sample_rate;
    *(float *)((uint8_t *)object + 0xcu) = 1.0f / (float)pitch_sample_rate;
    /* initialize() sizes its two working buffers from this field alone. The
       frame count getStreamAt hands us is not the audio device block size, so
       claim the largest block the hook will ever pass instead of the device's. */
    *(uint32_t *)((uint8_t *)object + 0x10u) = PITCH_MAX_FRAMES;
    ((pitch_initialize_fn)PITCH_INITIALIZE)(object);
    /* Level/depth scales the percentage curve, and the constructor leaves it at
       zero, which is total bypass: the effect ran but never moved a sample.
       0.5 is the curve's unity point and also selects the fully wet mix. */
    ((pitch_adjust_fn)PITCH_ADJUST_PARAMETER)(object, PITCH_PARAM_LEVEL_DEPTH,
                                              PITCH_UNITY_LEVEL_DEPTH);
    /* The constructor starts the percentage at -50. Publishing it through
       adjustParameter is what recalculates the ratio, the dry/wet ramps, and
       the shift direction, so it is also how the neutral state is reached. */
    publish_pitch_percent(object, context->semitones);
    context->pitch = object;
    context->pitch_output = output;
    return 0;
}

static void change_key(unsigned int deck, int delta)
{
    int value = keyshift_decks[deck].semitones + delta;
    if (value < -12)
        value = -12;
    if (value > 12)
        value = 12;
    if (value == keyshift_decks[deck].semitones)
        return;
    keyshift_decks[deck].semitones = value;
    keyshift_decks[deck].pitch_tail_blocks = 64u;
    /* This runs on the touch thread. adjustParameter rewrites the percentage,
       the dry/wet ramps, and the shift direction together, so the audio thread
       publishes it on a block boundary rather than mid-block. */
    keyshift_decks[deck].pitch_pending = 1;
    log_number(deck == 0 ? "deck 1 key index = " : "deck 2 key index = ",
               (unsigned long)(value + 12));
}

static void initialize_pitch_decks(void)
{
    for (unsigned int i = 0; i < 2u; i++) {
        destroy_pitch(&keyshift_decks[i]);
        if (create_pitch(&keyshift_decks[i]))
            log_number("pitch allocation failed on deck = ", i + 1u);
        if (!keyshift_decks[i].shifter.history) {
            float *history = mmap(0, RX3_SHIFT_HISTORY * 2u * sizeof(float),
                                  PROT_READ | PROT_WRITE,
                                  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
            if (history == MAP_FAILED)
                log_number("shifter allocation failed on deck = ", i + 1u);
            else
                rx3_shifter_init(&keyshift_decks[i].shifter, history);
        } else {
            rx3_shifter_init(&keyshift_decks[i].shifter,
                             keyshift_decks[i].shifter.history);
        }
        rx3_shifter_set_semitones(&keyshift_decks[i].shifter,
                                  keyshift_decks[i].semitones);
    }
}

/* Diagnostic scaling: log_number only carries unsigned values, so floats are
   reported in thousandths, biased by 1000 so a negative reads below 1000. */
static unsigned long scaled_signed(float value)
{
    return (unsigned long)(long)(1000.0f + value * 1000.0f);
}

static unsigned long scaled_peak(const Float2 *block, unsigned long frames)
{
    float peak = 0.0f;
    for (unsigned long i = 0; i < frames; i++) {
        float left = block[i].left < 0.0f ? -block[i].left : block[i].left;
        if (left > peak)
            peak = left;
    }
    return (unsigned long)(peak * 1000.0f);
}

static void apply_pitch(unsigned int deck, struct rx3_keyshift_deck *context,
                        Float2 *output, unsigned long frames)
{
    if (!RX3_ENABLE_PITCH || frames == 0 || frames > PITCH_MAX_FRAMES)
        return;
    uint64_t entered_us = RX3_PITCH_DIAGNOSTIC ? monotonic_enough_us() : 0;

    /* Publish a pending key change to both engines: whichever runs next has to
       already agree with what the operator asked for. */
    if (context->pitch_pending) {
        context->pitch_pending = 0;
        if (context->pitch)
            publish_pitch_percent(context->pitch, context->semitones);
        rx3_shifter_set_semitones(&context->shifter, context->semitones);
    }

    int native = RX3_USE_NATIVE_PITCH ||
                 (RX3_HYBRID_PITCH && context->semitones < 0);
    if (RX3_PITCH_DIAGNOSTIC) {
        pitch_in_peak[deck] = scaled_peak(output, frames);
        pitch_state_engaged[deck] = (unsigned long)native;
    }

    if (native) {
        /* Our ring keeps absorbing so a later change of direction starts from
           real audio rather than silence. */
        if (context->shifter.history)
            rx3_shifter_absorb(&context->shifter, (const float *)(void *)output,
                               (unsigned int)frames);
        if (!context->pitch || !context->pitch_output)
            return;
        if (context->semitones == 0 && context->pitch_tail_blocks == 0)
            return;
        ((pitch_execute_fn)PITCH_EXECUTE)(context->pitch, output,
                                         context->pitch_output, (int)frames);
        memcpy(output, context->pitch_output, frames * sizeof(Float2));
        if (context->semitones == 0 && context->pitch_tail_blocks)
            context->pitch_tail_blocks--;
    } else {
        if (!context->shifter.history)
            return;
        if (rx3_shifter_is_active(&context->shifter))
            rx3_shifter_process(&context->shifter, (float *)(void *)output,
                                (unsigned int)frames);
        else
            rx3_shifter_absorb(&context->shifter, (const float *)(void *)output,
                               (unsigned int)frames);
    }

    if (RX3_PITCH_DIAGNOSTIC) {
        pitch_out_peak[deck] = scaled_peak(output, frames);
        pitch_state_ratio[deck] = scaled_signed(context->shifter.ratio);
        unsigned long spent = (unsigned long)(monotonic_enough_us() - entered_us);
        unsigned long budget = frames * 1000000u / pitch_sample_rate;
        pitch_us_last[deck] = spent;
        pitch_budget_us[deck] = budget;
        if (spent > pitch_us_max[deck])
            pitch_us_max[deck] = spent;
        if (spent > budget)
            pitch_over_budget[deck]++;
    }
    pitch_execute_calls[deck]++;
    pitch_last_frames[deck] = frames;
}

/* The pitch stage: the resampler's output, one block of the deck's playback
   stream. Every block is offered, silent ones included, because skipping one
   would break the delay line's continuity. */
static void pitch_resampler_output(void *stretch, Float2 *output,
                                   unsigned int frames)
{
    int deck = deck_index_for_reader(
        *(void *const *)((const uint8_t *)stretch + 4u));
    if (deck < 0 || !output || frames == 0u)
        return;
    operate_calls++;
    operate_frames = frames;
    apply_pitch((unsigned int)deck, &keyshift_decks[deck], output, frames);
}

/* Varispeed and scratch playback. */
static long hooked_timestretch_operate(void *stretch, long position,
                                       Float2 *output, unsigned int frames)
{
    long result = original_timestretch_operate(stretch, position, output,
                                               frames);
    pitch_resampler_output(stretch, output, frames);
    return result;
}

/* The same stage while Master Tempo is on. */
static long hooked_timestretch_fgpr(void *stretch, long position,
                                    Float2 *output, unsigned int frames)
{
    long result = original_timestretch_fgpr(stretch, position, output, frames);
    pitch_resampler_output(stretch, output, frames);
    return result;
}

/* The core's watcher prints this; the module decides what is worth printing. */
static void rx3_keyshift_report(void)
{
    for (unsigned int deck = 0; deck < 2u; deck++) {
        if (!pitch_execute_calls[deck])
            continue;
        log_number("--- deck = ", deck + 1u);
        log_number("  key index = ",
                   (unsigned long)(keyshift_decks[deck].semitones + 12));
        log_number("  pitch blocks = ", pitch_execute_calls[deck]);
        log_number("  pitch frames = ", pitch_last_frames[deck]);
        log_number("  pitch us last = ", pitch_us_last[deck]);
        log_number("  pitch us max = ", pitch_us_max[deck]);
        log_number("  block us budget = ", pitch_budget_us[deck]);
        log_number("  over budget = ", pitch_over_budget[deck]);
        log_number("  in peak x1000 = ", pitch_in_peak[deck]);
        log_number("  out peak x1000 = ", pitch_out_peak[deck]);
        log_number("  ratio x1000 +1000 = ", pitch_state_ratio[deck]);
        log_number("  native engine = ", pitch_state_engaged[deck]);
    }
}

static uint16_t key_value[2][8];

static void format_key_value(unsigned int deck)
{
    uint16_t *text = key_value[deck];
    int value = keyshift_decks[deck].semitones;
    unsigned int n = 0;
    if (value > 0)
        text[n++] = '+';
    else if (value < 0) {
        text[n++] = '-';
        value = -value;
    }
    if (value >= 10)
        text[n++] = '1';
    text[n++] = (uint16_t)('0' + value % 10);
    text[n] = 0;
}

/* The KEY panel's centre label. Formatted here because the value's spelling --
   sign, and the only two-digit case -- belongs to the feature, not the panel. */
static const uint16_t *rx3_keyshift_label(unsigned int deck)
{
    if (deck >= 2u)
        return key_value[0];
    format_key_value(deck);
    return key_value[deck];
}

/* A new track on this deck. The engines keep their setting -- the operator's
   key survives a load -- but the native one needs its value republished, since
   its own state was built around the previous stream. */
static void rx3_keyshift_reload(unsigned int deck)
{
    if (deck >= 2u)
        return;
    keyshift_decks[deck].pitch_tail_blocks =
        keyshift_decks[deck].semitones ? 64u : 0u;
    if (keyshift_decks[deck].pitch)
        publish_pitch_percent(keyshift_decks[deck].pitch,
                              keyshift_decks[deck].semitones);
}

static int rx3_keyshift_semitones(unsigned int deck)
{
    return deck < 2u ? keyshift_decks[deck].semitones : 0;
}

static void rx3_keyshift_change(unsigned int deck, int delta)
{
    if (deck < 2u)
        change_key(deck, delta);
}

/* Called once the audio device format is known: the engines size their buffers
   from it, so they cannot be built before rbp starts its device. */
static void rx3_keyshift_start_audio(unsigned int sample_rate)
{
    pitch_sample_rate = sample_rate;
    initialize_pitch_decks();
    log_number("key shift sample rate = ", pitch_sample_rate);
    log_number("key shift buffer frames = ", PITCH_MAX_FRAMES);
}

static void rx3_keyshift_install(void)
{
    original_timestretch_operate = (timestretch_operate_fn)install_hook(
        &timestretch_operate_hook, TIMESTRETCH_OPERATE,
        timestretch_operate_guard, (void *)hooked_timestretch_operate);
    original_timestretch_fgpr = (timestretch_operate_fn)install_hook(
        &timestretch_fgpr_hook, TIMESTRETCH_FGPR_OPERATE,
        timestretch_fgpr_guard, (void *)hooked_timestretch_fgpr);
}

static int rx3_keyshift_ready(void)
{
    return original_timestretch_operate && original_timestretch_fgpr;
}

static void rx3_keyshift_remove(void)
{
    uninstall_hook(&timestretch_fgpr_hook);
    uninstall_hook(&timestretch_operate_hook);
    original_timestretch_fgpr = 0;
    original_timestretch_operate = 0;
    for (unsigned int deck = 0; deck < 2u; deck++)
        destroy_pitch(&keyshift_decks[deck]);
}

static void rx3_keyshift_destroy_deck(unsigned int deck)
{
    if (deck < 2u)
        destroy_pitch(&keyshift_decks[deck]);
}

#endif /* RX3_KEYSHIFT_H */
