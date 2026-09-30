/* SPDX-License-Identifier: MPL-2.0
 * Sample bank behaviour, private to rx3_samples_module.c: the bank, its
 * voices, the pad policy while its panel owns the pads, and its LEDs.
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

/* The bank loads as one job on the core's shared loader. */
static int samples_loader_stopping(void)
{
    return framework->loader->stopping(&samples_enabled);
}

static void samples_release_slot(unsigned int pad)
{
    struct sample_bank_slot *slot = &samples_bank[pad];
    __atomic_store_n(&slot->frames, 0, __ATOMIC_SEQ_CST);
    samples_slots[pad].position = SAMPLE_SLOT_IDLE;
    samples_slots[pad].frames = 0;
    samples_slots[pad].length = 0u;
    samples_slots[pad].mode = SAMPLE_MODE_ONCE;
    samples_slots[pad].gain = SAMPLES_GAIN_UNITY;
    if (slot->block) {
        munmap(slot->block, slot->block_size);
        framework->memory->release(&samples_enabled, slot->block_size);
    }
    memset(slot, 0, sizeof(*slot));
}

static void samples_load_bank(void *unused)
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
        if (samples_loader_stopping()) break;
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
        /* Recorded in the shared ledger; the bank's own 16 MiB ceiling is
           the limit, as it always was. */
        const struct rx3_memory_service *memory = framework->memory;
        void *block = memory->reserve(&samples_enabled, allocation, 0u)
            ? mmap(0, allocation, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0)
            : MAP_FAILED;
        if (block != MAP_FAILED) memcpy(block, audio, bytes);
        munmap(wave, (size_t)length);
        if (block == MAP_FAILED) {
            memory->abandon(&samples_enabled, allocation);
            continue;
        }
        if (mprotect(block, allocation, PROT_READ)) {
            munmap(block, allocation);
            memory->abandon(&samples_enabled, allocation);
            continue;
        }
        memory->settle(&samples_enabled, allocation);
        samples_bank[pad].length = bytes / SAMPLES_FRAME_BYTES;
        samples_bank[pad].block = block;
        samples_bank[pad].block_size = allocation;
        __atomic_store_n(&samples_bank[pad].frames, block, __ATOMIC_SEQ_CST);
        total += bytes;
        log_number("sample loaded, pad = ", pad + 1u);
    }
done:
    return;
}

/* The master bus already contains the player; the core calls this before its
   talkover attenuator runs. */
static void samples_master(struct rx3_stereo *output, unsigned int frames)
{
    if (__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST))
        samples_mix(samples_slots, output, (int)frames,
                    __atomic_load_n(&samples_volume, __ATOMIC_SEQ_CST));
}

/* Explicit silence is independent of panel and pad-mode navigation. */
static void samples_stop(int all)
{
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) {
        samples_pad_hold[pad] = 0u;
        if (all || __atomic_load_n(&samples_slots[pad].mode, __ATOMIC_SEQ_CST) !=
                   SAMPLE_MODE_ONCE)
            samples_voice_command(&samples_slots[pad], SAMPLE_SLOT_IDLE);
    }
}

static void samples_leave_mode(void)
{
    __atomic_store_n(&samples_mode, 0u, __ATOMIC_SEQ_CST);
}

/* SHIFT is watched, never consumed. */
static int samples_key(const struct rx3_key_event *event)
{
    if (event->key == RX3_KEY_SHIFT && event->operation == 0u &&
        __atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST) &&
        __atomic_load_n(&samples_config.shift_silence, __ATOMIC_SEQ_CST))
        samples_stop(1);
    return 0;
}

static unsigned int samples_active_voices(void)
{
    unsigned int count = 0u;
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++)
        if (samples_voice_position(&samples_slots[pad]) != SAMPLE_SLOT_IDLE)
            count++;
    return count;
}

/* While the SAMPLES panel is up the eight pads play the bank; a held pad's
   release is still taken after the panel closes. Everything else goes on to
   the next handler and to the player. */
static int samples_pad(const struct rx3_pad_event *event)
{
    unsigned int code = event->code, operation = event->operation;
    unsigned int owner_bit = 1u << (event->channel & 7u);
    if (!__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST) ||
        code < 0x4117u || code > 0x411eu ||
        (!__atomic_load_n(&samples_mode, __ATOMIC_SEQ_CST) &&
         !((operation & 0x0eu) == 2u && (samples_pad_hold[code - 0x4117u] & owner_bit))))
        return 0;
    unsigned int pad = code - 0x4117u;
    if (!operation) {
        if (__atomic_load_n(&samples_config.shift_silence, __ATOMIC_SEQ_CST) &&
            (framework->input->shift_held(1u) || framework->input->shift_held(2u))) {
            /* One press that stops everything, rather than eight. */
            samples_stop(1);
        } else {
            unsigned int mode = __atomic_load_n(&samples_config.mode[pad],
                                                 __ATOMIC_SEQ_CST);
            if (mode == SAMPLE_MODE_HOLD)
                samples_pad_hold[pad] |= owner_bit;
            unsigned int position = samples_voice_position(&samples_slots[pad]);
            const int16_t *data = __atomic_load_n(&samples_bank[pad].frames,
                                                  __ATOMIC_SEQ_CST);
            if ((mode == SAMPLE_MODE_LOOP || mode == SAMPLE_MODE_LATCH) &&
                position != SAMPLE_SLOT_IDLE) {
                /* Both modes that hold are stopped by the pad that
                   started them. The mixer tells them apart, not this:
                   only a loop wraps, and a latch runs out on its own. */
                samples_voice_command(&samples_slots[pad], SAMPLE_SLOT_IDLE);
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
                samples_voice_command(&samples_slots[pad], 0u);
            }
        }
    } else if ((operation & 0x0eu) == 2u &&
               __atomic_load_n(&samples_slots[pad].mode, __ATOMIC_SEQ_CST) ==
               SAMPLE_MODE_HOLD) {
        samples_pad_hold[pad] &= ~owner_bit;
        if (!samples_pad_hold[pad])
            samples_voice_command(&samples_slots[pad], SAMPLE_SLOT_IDLE);
    }
    return 1;
}

/* While the panel owns the pads: each pad in its bank colour, dimmed while
   idle, and SHIFT red. Every deck shows the same bank. */
static void samples_light(unsigned int deck, unsigned int control, struct rx3_light *light)
{
    (void)deck;
    if (!__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST) ||
        !__atomic_load_n(&samples_mode, __ATOMIC_SEQ_CST)) return;
    if (control == RX3_LIGHT_SHIFT) {
        light->state = RX3_LIGHT_ON;
        light->rgb = 0xff0000u;
    } else if (control < SAMPLES_PAD_COUNT) {
        light->rgb = __atomic_load_n(&samples_config.colour[control], __ATOMIC_SEQ_CST);
        light->state = samples_voice_position(&samples_slots[control]) == SAMPLE_SLOT_IDLE
            ? RX3_LIGHT_DIM : RX3_LIGHT_ON;
    }
}

/* The core shows the panel from the SAMPLES touchscreen tab and leaves it on
   every native navigation. Existing voices keep playing either way. */
static void samples_activate(unsigned int active)
{
    if (!active) {
        samples_leave_mode();
        return;
    }
    if (!__atomic_load_n(&samples_callbacks_enabled, __ATOMIC_SEQ_CST)) return;
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++)
        if (!samples_slots[pad].frames || !samples_slots[pad].length)
            samples_voice_command(&samples_slots[pad], SAMPLE_SLOT_IDLE);
    __atomic_store_n(&samples_mode, 1u, __ATOMIC_SEQ_CST);
    log_line("sample mode enabled");
}

/* The core detaches, drains and releases every shared hook before these
   calls return, so no callback can reach the payloads released after them. */
static void samples_feature_remove(void)
{
    __atomic_store_n(&samples_callbacks_enabled, 0u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&samples_mode, 0u, __ATOMIC_SEQ_CST);
    framework->panels->unregister_row(&samples_row);
    framework->audio->release_master(&samples_enabled);
    framework->input->unregister_owner(&samples_enabled);
    framework->loader->release(&samples_enabled);
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) samples_release_slot(pad);
}

static int samples_feature_install(void)
{
    const struct rx3_input_service *input = framework->input;
    if (!samples_enabled) return 0;
    struct samples_config defaults;
    samples_config_defaults(&defaults);
    samples_publish_config(&defaults);
    /* The physical pad-mode dispatcher is what lets a pad-mode key leave the
       panel on 1.19; without it the pads could be kept by the bank. */
    if (!input->claim_mode_keys(&samples_enabled)) {
        log_line("samples disabled: physical pad-mode dispatcher guard rejected");
        return 0;
    }
    if (!framework->audio->claim_master(&samples_enabled, samples_master)) return 0;
    /* Ahead of Stems: the bank owns the pads while its panel is up. */
    if (!input->register_pad(&samples_enabled, 10u, samples_pad)) return 0;
    if (!input->register_key(&samples_enabled, 10u, samples_key)) return 0;
    if (!input->register_lights(&samples_enabled, RX3_LIGHTS_PADS, samples_light))
        log_line("sample LEDs unavailable: guard rejected");
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++) {
        samples_slots[pad].position = SAMPLE_SLOT_IDLE;
        samples_slots[pad].gain = SAMPLES_GAIN_UNITY;
    }
    const struct rx3_load_job bank = {samples_load_bank, 0, 0};
    if (!framework->loader->claim(&samples_enabled) ||
        !framework->loader->submit(&samples_enabled, &bank)) return 0;
    __atomic_store_n(&samples_callbacks_enabled, 1u, __ATOMIC_SEQ_CST);
    if (!framework->panels->register_row(&samples_row)) return 0;
    log_line("sample playback installed; hardware validation pending");
    return 1;
}

#endif /* RX3_SAMPLES_FEATURE_H */
