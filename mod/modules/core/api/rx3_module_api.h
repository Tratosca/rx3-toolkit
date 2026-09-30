/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_MODULE_API_H
#define RX3_MODULE_API_H
#include "rx3_platform.h"
#include "rx3_hook_types.h"
#include "rx3_mix_types.h"
#include "rx3_notice_api.h"
#include "rx3_dsp.h"
#include "rx3_panel_api.h"
#include "rx3_image_api.h"
#include "rx3_browse_api.h"
#include "rx3_title_api.h"
#include "rx3_input_api.h"
#include "rx3_audio_api.h"
#include "rx3_memory_api.h"
#include "rx3_loader_api.h"
#define RX3_MODULE_API_VERSION 18u
/* Static composition contract, not a promise of a stable dynamic ABI.
 * All descriptors have process lifetime. Startup is serial and explicit.
 * A failed start is followed by stop, including partial installation.
 * No module calls another module or sees its descriptor/state.
 */
/* Render-thread observation; text is borrowed for this callback only. */
struct rx3_text_observation {
    unsigned int layer;
    uint16_t box[4];
    const uint16_t *text;
    unsigned int length;
};
struct rx3_services {
    void *(*install_hook)(struct installed_hook *, unsigned long,
                          const uint8_t[8], void *);
    int (*uninstall_hook)(struct installed_hook *);
    void (*log_line)(const char *);
    struct rx3_mix_state (*mix_state)(unsigned int deck);
    const struct rx3_notice_service *notices;
    const struct rx3_dsp_service *dsp;
    const struct rx3_panel_service *panels;
    /* Copies BLUE (format 0, stride 1), RGB (1, stride 2), legacy 3Band
       (2, stride 3), or PWV7 (3, stride 3) columns on the native 150 Hz grid. Never
       returns a provider pointer. count must equal the complete track axis.
       Returns 0 for unavailable, count on success, UINT32_MAX for axis mismatch. */
    /* 0xfffffffe: intentional audio-only package, preserve native display.
       0xffffffff: incompatible column axis. A count=0 probe writes nothing. */
    unsigned int (*waveform)(unsigned int deck, unsigned int mask, unsigned int format, uint8_t *out, unsigned int count);
    int (*detach_hook)(struct installed_hook *);
    int (*release_hook)(struct installed_hook *);
    const struct rx3_image_service *images;
    const struct rx3_browse_service *browse;
    const struct rx3_title_service *titles;
    const struct rx3_input_service *input;
    const struct rx3_audio_service *audio;
    void (*log_number)(const char *label, unsigned long value);
    const struct rx3_memory_service *memory;
    /* Firmware bytes (at most eight) are replaced only while they still hold
       `expected`; the previous bytes survive any failure. Serial startup,
       shutdown or the render thread only. Null when unavailable. */
    int (*write_guarded)(unsigned long address, const void *expected,
                         const void *replacement, unsigned int length);
    /* The single provider behind mix_state() and waveform(). A second
       provider is refused; only the current one can withdraw. Readers run on
       render and waveform threads: no allocation, I/O or waiting. */
    int (*provide_mix)(struct rx3_mix_state (*)(unsigned int deck));
    void (*withdraw_mix)(struct rx3_mix_state (*)(unsigned int deck));
    int (*provide_waveform)(unsigned int (*)(unsigned int deck, unsigned int mask,
                            unsigned int format, uint8_t *out, unsigned int count));
    void (*withdraw_waveform)(unsigned int (*)(unsigned int deck, unsigned int mask,
                              unsigned int format, uint8_t *out, unsigned int count));    const struct rx3_loader_service *loader;
};
struct rx3_module {
    unsigned int version;
    unsigned int size;
    const char *name;
    int (*configured)(void);
    int (*start)(const struct rx3_services *);
    void (*stop)(void);
    /* On the native load thread, after the original load and providers. */
    void (*track_did_load)(unsigned int deck, void *reader, const void *track_info);
    /* Audio device callback, after the native format has been established. */
    void (*audio_started)(unsigned int sample_rate);
    void (*text_observed)(const struct rx3_text_observation *);
    /* Diagnostic worker; must not mutate audio state. */
    void (*report)(void);
    /* Invalidate old metadata before the native load can publish new text. */
    void (*track_will_load)(unsigned int deck, void *reader, const void *track_info);
};
#endif
