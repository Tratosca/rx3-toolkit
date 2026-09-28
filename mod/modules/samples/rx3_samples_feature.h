/* SPDX-License-Identifier: MPL-2.0
 * Sample bank implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_SAMPLES_FEATURE_H
#define RX3_SAMPLES_FEATURE_H

static int samples_enabled;

#include "rx3_samples_config.h"
#include "rx3_samples_audio.h"

static void samples_publish_config(const struct samples_config *wanted)
{
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++)
        __atomic_store_n(&samples_config.colour[pad], wanted->colour[pad], __ATOMIC_SEQ_CST);
    __atomic_store_n(&samples_config.volume, wanted->volume, __ATOMIC_SEQ_CST);
    if (!__atomic_load_n(&samples_volume_touched, __ATOMIC_SEQ_CST))
        __atomic_store_n(&samples_volume, wanted->volume, __ATOMIC_SEQ_CST);
}

static void samples_read_config(const char *path, struct samples_config *into)
{
    samples_config_defaults(into);
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        log_line("sample: no settings.ini, compiled defaults active");
        return;
    }
    off_t length = lseek(fd, 0, SEEK_END);
    int valid = length > 0 && (unsigned long)length <= SAMPLES_CONFIG_MAX_BYTES &&
        lseek(fd, 0, SEEK_SET) == 0;
    char buffer[SAMPLES_CONFIG_MAX_BYTES];
    size_t total = 0u;
    while (valid && total < (size_t)length) {
        ssize_t got = read(fd, buffer + total, (size_t)length - total);
        if (got <= 0) {
            valid = 0;
            break;
        }
        total += (size_t)got;
    }
    close(fd);
    if (!valid || !samples_parse_config(buffer, total, into)) {
        log_line("sample: settings.ini rejected, compiled defaults active");
        return;
    }
    log_line("sample: settings.ini version 1 active");
}

static int samples_feature_configured(void)
{
    return samples_enabled;
}

static struct installed_hook samples_audio_hook;
static struct installed_hook samples_led_hook;
static void (*original_mic_talkover_attenuate)(void *, void *, Float2 *, int);
static check_slip_led_fn original_check_led_stat;
static pthread_t samples_loader_thread;
static int samples_loader_started;
static volatile unsigned int samples_loader_running;
static int samples_owns_pad;
static int samples_owns_send_key;

static void samples_release_slot(unsigned int pad)
{
    struct sample_bank_slot *slot = &samples_bank[pad];
    __atomic_store_n(&slot->frames, 0, __ATOMIC_SEQ_CST);
    samples_slots[pad].position = SAMPLE_SLOT_IDLE;
    samples_slots[pad].frames = 0;
    samples_slots[pad].length = 0u;
    samples_slots[pad].mode = SAMPLE_MODE_ONCE;
    samples_slots[pad].gain = SAMPLES_GAIN_UNITY;
    if (slot->block) munmap(slot->block, slot->block_size);
    memset(slot, 0, sizeof(*slot));
}

static void *samples_loader_loop(void *unused)
{
    (void)unused;
    struct samples_config wanted;
    const char *config = getenv("RX3_SAMPLES_CONFIG");
    samples_read_config(config ? config : "", &wanted);
    samples_publish_config(&wanted);
    const char *directory = getenv("RX3_SAMPLES_DIR");
    size_t prefix = directory ? str_length(directory) : 0u;
    char path[1024];
    unsigned int total = 0u;
    if (!prefix || prefix + 7u > sizeof(path)) goto done;
    memcpy(path, directory, prefix);
    memcpy(path + prefix, "/1.wav", 7u);
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) {
        if (!__atomic_load_n(&samples_loader_running, __ATOMIC_SEQ_CST)) break;
        samples_release_slot(pad);
        path[prefix + 1u] = (char)('1' + pad);
        int fd = open(path, O_RDONLY);
        if (fd < 0) continue;
        off_t length = lseek(fd, 0, SEEK_END);
        if (length < 12 || (unsigned long)length > SAMPLES_BANK_MAX_BYTES) {
            close(fd);
            continue;
        }
        void *wave = mmap(0, (size_t)length, PROT_READ, MAP_PRIVATE, fd, 0);
        close(fd);
        if (wave == MAP_FAILED) continue;
        unsigned int bytes;
        const uint8_t *audio = samples_wave_data(wave, (size_t)length, &bytes);
        if (!audio || bytes > SAMPLES_BANK_MAX_BYTES - total) {
            munmap(wave, (size_t)length);
            continue;
        }
        size_t allocation = (bytes + 4095u) & ~4095u;
        void *block = mmap(0, allocation, PROT_READ | PROT_WRITE,
                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (block != MAP_FAILED) memcpy(block, audio, bytes);
        munmap(wave, (size_t)length);
        if (block == MAP_FAILED) continue;
        if (mprotect(block, allocation, PROT_READ)) {
            munmap(block, allocation);
            continue;
        }
        samples_bank[pad].length = bytes / SAMPLES_FRAME_BYTES;
        samples_bank[pad].block = block;
        samples_bank[pad].block_size = allocation;
        __atomic_store_n(&samples_bank[pad].frames, block, __ATOMIC_SEQ_CST);
        total += bytes;
        log_number("sample loaded, pad = ", pad + 1u);
    }
done:
    __atomic_store_n(&samples_loader_running, 0u, __ATOMIC_SEQ_CST);
    return 0;
}

static void hooked_mic_talkover_attenuate(void *self, void *state,
                                          Float2 *output, int frames)
{
    __sync_add_and_fetch(&samples_audio_active, 1u);
    if (__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST))
        samples_mix(samples_slots, output, frames,
                    __atomic_load_n(&samples_volume, __ATOMIC_SEQ_CST));
    original_mic_talkover_attenuate(self, state, output, frames);
    __sync_sub_and_fetch(&samples_audio_active, 1u);
}

/* Explicit silence is independent of panel and pad-mode navigation. */
static void samples_stop(int all)
{
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) {
        samples_pad_hold[pad] = 0u;
        if (all || __atomic_load_n(&samples_slots[pad].mode, __ATOMIC_SEQ_CST) !=
                   SAMPLE_MODE_ONCE)
            __atomic_store_n(&samples_slots[pad].position, SAMPLE_SLOT_IDLE,
                               __ATOMIC_SEQ_CST);
    }
}

static void samples_leave_mode(void)
{
    __atomic_store_n(&samples_mode, 0u, __ATOMIC_SEQ_CST);
}

static void samples_shift_pressed(void)
{
    if (__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST) &&
        __atomic_load_n(&samples_config.shift_silence, __ATOMIC_SEQ_CST))
        samples_stop(1);
}

static unsigned int samples_active_voices(void)
{
    unsigned int count = 0u;
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++)
        if (__atomic_load_n(&samples_slots[pad].position, __ATOMIC_SEQ_CST) != SAMPLE_SLOT_IDLE)
            count++;
    return count;
}

static int hooked_on_key_pad(void *self, const void *input)
{
    __sync_add_and_fetch(&pad_callbacks_active, 1u);
    const uint8_t *event = input;
    unsigned int code = event[8] | ((unsigned int)event[9] << 8u);
    int result;
    if (__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST) &&
        code >= 0x4117u && code <= 0x411eu &&
        (__atomic_load_n(&samples_mode, __ATOMIC_SEQ_CST) ||
         ((event[11] & 0x0eu) == 2u &&
          (samples_pad_hold[code - 0x4117u] & (1u << (event[10] & 7u)))))) {
        unsigned int pad = code - 0x4117u;
        if (!(event[11] & 0x0fu)) {
            if (__atomic_load_n(&samples_config.shift_silence, __ATOMIC_SEQ_CST) &&
                (theme_shift_held[1] || theme_shift_held[2])) {
                /* One press that stops everything, rather than eight. */
                samples_stop(1);
            } else {
                unsigned int mode = __atomic_load_n(&samples_config.mode[pad],
                                                     __ATOMIC_SEQ_CST);
                if (mode == SAMPLE_MODE_HOLD)
                    samples_pad_hold[pad] |= 1u << (event[10] & 7u);
                unsigned int position = __atomic_load_n(&samples_slots[pad].position,
                                                         __ATOMIC_SEQ_CST);
                const int16_t *data = __atomic_load_n(&samples_bank[pad].frames,
                                                      __ATOMIC_SEQ_CST);
                if ((mode == SAMPLE_MODE_LOOP || mode == SAMPLE_MODE_LATCH) &&
                    position != SAMPLE_SLOT_IDLE) {
                    /* Both modes that hold are stopped by the pad that
                       started them. The mixer tells them apart, not this:
                       only a loop wraps, and a latch runs out on its own. */
                    __atomic_store_n(&samples_slots[pad].position, SAMPLE_SLOT_IDLE,
                                       __ATOMIC_SEQ_CST);
                } else if (data && samples_bank[pad].length &&
                           (position != SAMPLE_SLOT_IDLE ||
                            samples_active_voices() < SAMPLES_MAX_VOICES)) {
                    samples_slots[pad].frames = data;
                    samples_slots[pad].length = samples_bank[pad].length;
                    /* The mode lands before the cursor does, so the mixer never
                       sees a sounding voice carrying the previous mode. */
                    __atomic_store_n(&samples_slots[pad].mode, mode, __ATOMIC_SEQ_CST);
                    __atomic_store_n(&samples_slots[pad].gain,
                                       __atomic_load_n(&samples_config.gain[pad],
                                                        __ATOMIC_SEQ_CST),
                                       __ATOMIC_SEQ_CST);
                    __atomic_store_n(&samples_slots[pad].position, 0u, __ATOMIC_SEQ_CST);
                }
            }
        } else if ((event[11] & 0x0eu) == 2u &&
                   __atomic_load_n(&samples_slots[pad].mode, __ATOMIC_SEQ_CST) ==
                   SAMPLE_MODE_HOLD) {
            samples_pad_hold[pad] &= ~(1u << (event[10] & 7u));
            if (!samples_pad_hold[pad])
                __atomic_store_n(&samples_slots[pad].position, SAMPLE_SLOT_IDLE,
                                   __ATOMIC_SEQ_CST);
        }
        result = 1;
    } else {
        result = stems_on_key_pad(self, input);
    }
    __sync_sub_and_fetch(&pad_callbacks_active, 1u);
    return result;
}

static void hooked_check_led_stat(void *self, void *state)
{
    __sync_add_and_fetch(&pad_callbacks_active, 1u);
    original_check_led_stat(self, state);
    if (!__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST) ||
        !__atomic_load_n(&samples_mode, __ATOMIC_SEQ_CST) || !state) goto done;
    unsigned int count = *(const uint16_t *)((const uint8_t *)state + 4u);
    uint8_t *entries = *(uint8_t **)((uint8_t *)state + 8u);
    if (!entries || !count || count > 256u) goto done;
    unsigned int base = 1u;
    for (unsigned int i = 0; i < count; i++) {
        unsigned int id = *(const uint32_t *)(entries + i * 44u);
        if (id >= 18u && id <= 25u) base = 18u;
    }
    for (unsigned int i = 0; i < count; i++) {
        uint8_t *led = entries + i * 44u;
        unsigned int id = *(const uint32_t *)led;
        unsigned int rgb, idle = 0u;
        if (id == 14u) {
            rgb = 0xff0000u;
        } else if (id >= base && id < base + 8u) {
            unsigned int pad = id - base;
            rgb = __atomic_load_n(&samples_config.colour[pad], __ATOMIC_SEQ_CST);
            idle = __atomic_load_n(&samples_slots[pad].position,
                                    __ATOMIC_SEQ_CST) == SAMPLE_SLOT_IDLE;
        } else continue;
        struct stems_rgb colour = {(uint8_t)(rgb >> 16u), (uint8_t)(rgb >> 8u),
                                    (uint8_t)rgb};
        ((set_led_state_fn)SET_LED_STATE)(led, LED_ON, 0, 0, 0, 0);
        ((set_led_color_fn)SET_LED_COLOR)(led, LED_ON, idle, &colour);
    }
done:
    __sync_sub_and_fetch(&pad_callbacks_active, 1u);
}

/* Entered by the SAMPLES touchscreen tab. Existing voices keep playing. */
static int samples_enter_mode(void)
{
    if (!__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST)) return 0;
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++)
        if (!samples_slots[pad].frames || !samples_slots[pad].length)
            __atomic_store_n(&samples_slots[pad].position, SAMPLE_SLOT_IDLE,
                               __ATOMIC_SEQ_CST);
    __atomic_store_n(&samples_mode, 1u, __ATOMIC_SEQ_CST);
    select_custom_panel(3u);
    log_line("sample mode enabled");
    return 1;
}

/* Detach first, then drain callbacks, then release code and payloads. A failed
   restore retains its trampoline because the replacement remains reachable. */
static int samples_detach_hook(struct installed_hook *hook)
{
    return detach_hook(hook);
}

static void samples_free_hook(struct installed_hook *hook)
{
    (void)release_hook(hook);
}

static void samples_feature_remove(void)
{
    __atomic_store_n(&samples_callbacks_enabled, 0u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&samples_mode, 0u, __ATOMIC_SEQ_CST);
    int audio_detached = samples_detach_hook(&samples_audio_hook);
    int led_detached = samples_detach_hook(&samples_led_hook);
    int pad_detached = !samples_owns_pad || samples_detach_hook(&pad_hook);
    for (;;) {
        while (__atomic_load_n(&pad_callbacks_active, __ATOMIC_SEQ_CST) ||
               __atomic_load_n(&samples_audio_active, __ATOMIC_SEQ_CST)) usleep(10000u);
        usleep(10000u);
        if (!__atomic_load_n(&pad_callbacks_active, __ATOMIC_SEQ_CST) &&
            !__atomic_load_n(&samples_audio_active, __ATOMIC_SEQ_CST)) break;
    }
    __atomic_store_n(&samples_loader_running, 0u, __ATOMIC_SEQ_CST);
    if (samples_loader_started) {
        pthread_join(samples_loader_thread, 0);
        samples_loader_started = 0;
    }
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) samples_release_slot(pad);
    if (audio_detached) {
        samples_free_hook(&samples_audio_hook);
        original_mic_talkover_attenuate = 0;
    }
    if (led_detached) {
        samples_free_hook(&samples_led_hook);
        original_check_led_stat = 0;
    }
    if (samples_owns_pad && pad_detached) {
        samples_free_hook(&pad_hook);
        original_on_key_pad = 0;
        samples_owns_pad = 0;
    }
    if (samples_owns_send_key) {
        uninstall_hook(&send_key_hook);
        if (!hook_is_installed(&send_key_hook)) {
            original_send_key = 0;
            samples_owns_send_key = 0;
        }
    }
}

static int samples_feature_install(void)
{
    static const uint8_t audio_guard[8] = {0x03,0xc0,0xd0,0xe5,0x04,0x40,0x2d,0xe5};
    static const uint8_t led_guard[8] = {0xf0,0x4f,0x2d,0xe9,0x00,0x40,0xa0,0xe1};
    if (!samples_enabled) return 0;
    struct samples_config defaults;
    samples_config_defaults(&defaults);
    samples_publish_config(&defaults);
    original_mic_talkover_attenuate = install_hook(
        &samples_audio_hook, 0x0009c750u, audio_guard,
        (void *)hooked_mic_talkover_attenuate);
    if (!original_mic_talkover_attenuate) return 0;
    if (!original_on_key_pad) {
        original_on_key_pad = install_hook(&pad_hook, ON_KEY_PAD, pad_guard,
                                            (void *)hooked_on_key_pad);
        samples_owns_pad = original_on_key_pad != 0;
        if (!original_on_key_pad) return 0;
    }
    if (!original_send_key) {
        original_send_key = install_hook(&send_key_hook, SEND_KEY, send_key_guard,
                                          (void *)hooked_send_key);
        samples_owns_send_key = original_send_key != 0;
        if (!original_send_key) return 0;
    }
    original_check_led_stat = install_hook(&samples_led_hook, 0x002f6318u,
                                            led_guard, (void *)hooked_check_led_stat);
    if (!original_check_led_stat) log_line("sample LEDs unavailable: guard rejected");
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) {
        samples_slots[pad].position = SAMPLE_SLOT_IDLE;
        samples_slots[pad].gain = SAMPLES_GAIN_UNITY;
    }
    __atomic_store_n(&samples_loader_running, 1u, __ATOMIC_SEQ_CST);
    if (pthread_create(&samples_loader_thread, 0, samples_loader_loop, 0)) {
        samples_loader_running = 0u;
        return 0;
    }
    samples_loader_started = 1;
    __atomic_store_n(&samples_callbacks_enabled, 1u, __ATOMIC_SEQ_CST);
    log_line("sample playback installed; hardware validation pending");
    return 1;
}

#endif /* RX3_SAMPLES_FEATURE_H */
