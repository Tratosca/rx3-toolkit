/* SPDX-License-Identifier: MPL-2.0 */
/* Stems. The module owns its files, formats, resident payloads, per-deck mix,
 * pad and LED policy, panel and loading indication. The core owns the native
 * stream, pad and LED hooks, deck identity and track notifications.
 *
 * Stems are copied into anonymous RAM before publication to the audio thread,
 * so removing the USB drive after a completed load leaves no file mapping.
 * PcmReader runs at 44,100 frames per second and ReaderImpl converts sources
 * before it, so the stem frame index shares the deck's time domain for 44.1,
 * 48 and 96 kHz files. Instrumental is the full mix minus the prepared roles;
 * both come from the same decode path to keep phase, delay and gain aligned.
 */
#include "../core/api/rx3_module_api.h"
static const struct rx3_services *framework;
#define log_line framework->log_line
#define log_number framework->log_number
#define TAB_IMAGE_STEMS 0x1601u

static size_t str_length(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

struct rx3_timeval { long seconds, microseconds; };
/* juce::Time::currentTimeMillis, which the panel compares the LED blink
   against, is gettimeofday reduced to milliseconds. */
static unsigned int now_ms(void)
{
    struct rx3_timeval value;
    if (gettimeofday(&value, 0))
        return 0;
    return (unsigned int)(((uint64_t)(unsigned long)value.seconds * 1000000u +
                           (uint64_t)(unsigned long)value.microseconds) / 1000u);
}

#include "rx3_stems_decl.h"

static int stems_deck_loading(const struct stems_deck_context *context)
{
    return context->reader && context->armed && !context->payloads[0].data;
}

static int stems_any_deck_loading(void)
{
    return stems_deck_loading(&stems_decks[0]) || stems_deck_loading(&stems_decks[1]);
}

/* The shared blink clock: the pads blink in the panel from the same origin
   the core gives the on-screen toggles, so the two cannot drift apart. */
static int blink_phase_is_on(void)
{
    return framework->input->blink_on();
}

/* Nothing of this module blinks: the next indication starts on its on phase. */
static void stems_blink_idle(void)
{
    framework->input->blink_restart();
}

static void release_payload(struct stem_payload *payload)
{
    if (payload->block) {
        munmap(payload->block, payload->block_size);
        framework->memory->release(&stems_decks, payload->block_size);
    }
    memset(payload, 0, sizeof(*payload));
}

static int path_in_stems(const char *filename, size_t filename_length,
                         char *output, size_t capacity)
{
    size_t n = 0;
    while (stems_dir[n] && n + 1u < capacity) {
        output[n] = stems_dir[n];
        n++;
    }
    if (stems_dir[n] || n + 2u + filename_length > capacity)
        return -1;
    if (n && output[n - 1u] != '/')
        output[n++] = '/';
    for (size_t i = 0; i < filename_length; i++)
        output[n++] = filename[i];
    output[n] = '\0';
    return 0;
}

/* StTrackInfo starts with an inline NUL-terminated path. ReaderImpl::loadFile
   passes it directly to endsWithIgnoreCase, which calls strlen(r0), and then
   to createSourceInputStream. Derive only the basename:
     /USB/Artist - Title.aiff -> $RX3_STEMS_DIR/Artist - Title.rx3stem */
static int stem_path_for_track(const void *track_info, char *output,
                                  size_t capacity)
{
    const char *track_path = (const char *)track_info;
    if (!track_path || !track_path[0] || !stems_dir || capacity < 16u)
        return -1;

    const char *base = track_path;
    const char *dot = 0;
    for (const char *p = track_path; *p; p++) {
        if (*p == '/' || *p == '\\') {
            base = p + 1;
            dot = 0;
        } else if (*p == '.') {
            dot = p;
        }
    }
    if (!base[0])
        return -1;
    const char *name_end = base + str_length(base);
    const char *end = dot && dot > base ? dot : name_end;
    char filename[768];
    size_t n = 0;
    while (base < end && n + 1u < sizeof(filename))
        filename[n++] = *base++;
    static const char suffix[] = ".rx3stem";
    for (size_t i = 0; i < sizeof(suffix); i++) {
        if (n + i >= sizeof(filename))
            return -1;
        filename[n + i] = suffix[i];
    }
    return path_in_stems(filename, n + sizeof(suffix) - 1u, output, capacity);
}

#include "rx3_stems_panel.h"
#include "rx3_stems_feature.h"

static int stems_configured(void)
{
    const char *directory = getenv("RX3_STEMS_DIR");
    return directory && directory[0];
}

static int stems_start(const struct rx3_services *services)
{
    framework = services;
    if (!services->audio || !services->input || !services->panels ||
        !services->provide_mix || !services->provide_waveform || !services->memory ||
        !services->loader) return 0;
    stems_dir = getenv("RX3_STEMS_DIR");
    if (stems_dir && !stems_dir[0]) stems_dir = 0;
    if (!stems_dir) return 0;
    return stems_feature_install();
}

static void stems_stop(void)
{
    if (!framework || !framework->audio || !framework->input || !framework->panels ||
        !framework->withdraw_mix || !framework->withdraw_waveform || !framework->loader) return;
    stems_feature_remove();
}

const struct rx3_module rx3_stems_module = {
    .version = RX3_MODULE_API_VERSION, .size = sizeof(struct rx3_module),
    .name = "stems", .configured = stems_configured,
    .start = stems_start, .stop = stems_stop,
    .track_did_load = stems_feature_track_did_load,
    .track_will_load = stems_feature_track_will_load
};
