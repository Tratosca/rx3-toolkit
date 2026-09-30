/* SPDX-License-Identifier: MPL-2.0
 *
 * Key shift for the RX3 performance runtime: implementation.
 *
 * Private implementation compiled by rx3_keyshift_module.c.
 *
 * The manager produces one block for either playback mode. Its position also
 * identifies jumps and direction changes that invalidate the shifter history.
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
    if (context->shifter.history) {
        munmap(context->shifter.history, RX3_SHIFT_HISTORY * 2u * sizeof(float));
        memset(&context->shifter, 0, sizeof(context->shifter));
    }
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
    publish_pitch_percent(object, ((int)(__atomic_load_n(&context->request, __ATOMIC_SEQ_CST) & 0xffu) - 12));
    context->pitch = object;
    context->pitch_output = output;
    return 0;
}

static void change_key(unsigned int deck, int delta)
{
    struct rx3_keyshift_deck *context = &keyshift_decks[deck];
    unsigned int request = __atomic_load_n(&context->request, __ATOMIC_SEQ_CST);
    for (;;) {
        int value = (int)(request & 0xffu) - 12 + delta;
        if (value < -12) value = -12;
        if (value > 12) value = 12;
        if (value == (int)(request & 0xffu) - 12) return;
        unsigned int next = ((request & ~0xffu) + 0x100u) | (unsigned int)(value + 12);
        if (__atomic_compare_exchange_n(&context->request, &request, next, 0,
                                         __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) {
            log_number(deck == 0u ? "deck 1 key index = " : "deck 2 key index = ",
                       (unsigned int)(value + 12));
            return;
        }
    }
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
                                  rx3_keyshift_semitones(i));
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

    unsigned int request = __atomic_load_n(&context->request, __ATOMIC_SEQ_CST);
    int semitones = (int)(request & 0xffu) - 12;
    if (request != context->applied_request) {
        if (context->pitch) publish_pitch_percent(context->pitch, semitones);
        rx3_shifter_set_semitones(&context->shifter, semitones);
        context->applied_request = request;
        context->pitch_tail_blocks = semitones ? 64u : 0u;
    }

    int native = RX3_USE_NATIVE_PITCH ||
                 (RX3_HYBRID_PITCH && semitones < 0);
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
        if (((int)(__atomic_load_n(&context->request, __ATOMIC_SEQ_CST) & 0xffu) - 12) == 0 && context->pitch_tail_blocks == 0)
            return;
        ((pitch_execute_fn)PITCH_EXECUTE)(context->pitch, output,
                                         context->pitch_output, (int)frames);
        memcpy(output, context->pitch_output, frames * sizeof(Float2));
        if (((int)(__atomic_load_n(&context->request, __ATOMIC_SEQ_CST) & 0xffu) - 12) == 0 && context->pitch_tail_blocks)
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

/* All reset decisions run on the audio thread. The UI publishes only counters. */
static int keyshift_transport_reset(struct rx3_keyshift_deck *context,
                                     uint32_t position, unsigned int frames,
                                     int silent)
{
    unsigned int generation = __atomic_load_n(&context->reset_generation, __ATOMIC_SEQ_CST);
    int reset = generation != context->seen_reset || (!silent && context->was_silent);
    context->seen_reset = generation;
    context->was_silent = silent;
    if (context->position_valid) {
        int delta = (int)(position - context->last_position);
        int span = (int)(frames > context->last_frames ? frames : context->last_frames) * 4;
        if (delta < -span || delta > span) reset = 1;
        int direction = delta > 0 ? 1 : delta < 0 ? -1 : 0;
        if (direction) {
            if (context->last_direction && direction != context->last_direction) reset = 1;
            context->last_direction = direction;
        }
    }
    context->position_valid = 1;
    context->last_position = position;
    context->last_frames = frames;
    return reset;
}

static long hooked_timestretch_manager(void *manager, uint32_t position,
                                        Float2 *output, unsigned int frames,
                                        unsigned int mode)
{
    __sync_add_and_fetch(&keyshift_callbacks_active, 1u);
    long result = original_timestretch_manager(manager, position, output, frames, mode);
    if (__atomic_load_n(&keyshift_callbacks_enabled, __ATOMIC_SEQ_CST) &&
        output && frames && frames <= PITCH_MAX_FRAMES) {
        unsigned int deck = *(const uint32_t *)manager;
        if (deck < 2u) {
            struct rx3_keyshift_deck *context = &keyshift_decks[deck];
            int silent = block_is_silent(output, frames);
            if (keyshift_transport_reset(context, position, frames, silent)) {
                int semitones = rx3_keyshift_semitones(deck);
                if (context->shifter.history) {
                    rx3_shifter_seed(&context->shifter, context->shifter.history,
                                     (const float *)(const void *)output, frames);
                    rx3_shifter_set_semitones(&context->shifter, semitones);
                    context->shifter.ratio = context->shifter.target;
                }
                if (context->pitch) publish_pitch_percent(context->pitch, semitones);
            }
            operate_calls++;
            operate_frames = frames;
            apply_pitch(deck, context, output, frames);
        }
    }
    __sync_sub_and_fetch(&keyshift_callbacks_active, 1u);
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
                   (unsigned long)(rx3_keyshift_semitones(deck) + 12));
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

/* Track replacement returns to neutral and invalidates history at the next block. */
static void rx3_keyshift_reload(unsigned int deck)
{
    if (deck >= 2u) return;
    change_key(deck, -rx3_keyshift_semitones(deck));
    __sync_add_and_fetch(&keyshift_decks[deck].reset_generation, 1u);
}

static int rx3_keyshift_semitones(unsigned int deck)
{
    return deck < 2u ? (int)(__atomic_load_n(&keyshift_decks[deck].request,
                                            __ATOMIC_SEQ_CST) & 0xffu) - 12 : 0;
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
    original_timestretch_manager = (timestretch_manager_fn)install_hook(
        &timestretch_manager_hook, TIMESTRETCH_MANAGER,
        timestretch_manager_guard, (void *)hooked_timestretch_manager);
    if (original_timestretch_manager)
        __atomic_store_n(&keyshift_callbacks_enabled, 1u, __ATOMIC_SEQ_CST);
}

static int rx3_keyshift_ready(void)
{
    return original_timestretch_manager != 0;
}

static void rx3_keyshift_remove(void)
{
    __atomic_store_n(&keyshift_callbacks_enabled, 0u, __ATOMIC_SEQ_CST);
    if (!detach_hook(&timestretch_manager_hook))
        return;
    for (;;) {
        while (__atomic_load_n(&keyshift_callbacks_active, __ATOMIC_SEQ_CST)) usleep(10000u);
        usleep(10000u);
        if (!__atomic_load_n(&keyshift_callbacks_active, __ATOMIC_SEQ_CST)) break;
    }
    (void)release_hook(&timestretch_manager_hook);
    original_timestretch_manager = 0;
    for (unsigned int deck = 0; deck < 2u; deck++) destroy_pitch(&keyshift_decks[deck]);
}


#endif /* RX3_KEYSHIFT_H */
