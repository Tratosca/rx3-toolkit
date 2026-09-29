// SPDX-License-Identifier: MPL-2.0
/*
 * Modular two-deck performance core for the XDJ-RX3.
 *
 * The core is the sole broker for guarded inline hooks, deck identity, native
 * rendering and touch routing. Optional Stems and Key Shift features own
 * disjoint state and hook groups and can fail independently.
 *
 * Both pads blink while a stem is being read and hold their colour once it
 * is resident, so the operator can see when the toggles become effective.
 *
 * Stems are copied into anonymous RAM before publication to the audio
 * thread. Removing the USB drive after a completed load therefore leaves no
 * active file mapping. int16 and float32 payloads are supported.
 *
 * PcmReader operates at 44,100 frames per second. ReaderImpl converts source
 * files before this buffer, so the stem frame index remains in the same
 * time domain for 44.1, 48, and 96 kHz input files.
 *
 * Instrumental output is full mix minus vocal. Both signals must originate
 * from the same decode path to preserve phase, delay, and gain alignment.
 * The resulting stream is then passed through rbp's native BeatEffectPitch,
 * independently for each deck. The performance overlay clones an existing
 * NS_GlyphText object, so text, rectangles, fonts, and clipping stay inside
 * rbp's own UI renderer.
 */

#define GET_STREAM_AT ((unsigned long)0x0003d1e0)
#define PCM_LOAD      ((unsigned long)0x00038ff0)
#define ON_KEY_PAD    ((unsigned long)0x003060e8)
#define ON_KEY_HOT_CUE ((unsigned long)0x003030ec)
#define ON_KEY_BEAT_LOOP ((unsigned long)0x003031cc)
#define ON_KEY_SLIP_LOOP ((unsigned long)0x00303238)
#define ON_KEY_BEAT_JUMP ((unsigned long)0x00303294)
#define CHECK_SLIP_LED ((unsigned long)0x002fcc04)
#define SET_LED_COLOR  ((unsigned long)0x0033e4f8)
#define SET_LED_STATE  ((unsigned long)0x0033e3f4)
#define PAL_DRAW_TEXT  ((unsigned long)0x001d23e4)
#define PAL_DRAW_IMAGE ((unsigned long)0x001d3284)
#define SOLVE_TOUCH    ((unsigned long)0x002dc104)
#define BEATFX_XPAD_CTOR ((unsigned long)0x0035b0f8)
#define AUDIO_START    ((unsigned long)0x000447b8)
/* Recovered from a released build, not measured here. Unverified on hardware:
   see docs/recovering-a-module.md before this is quoted anywhere as evidence. */
#define HW_FILL_RECT ((unsigned long)0x001a46dc)
#define SEND_KEY ((unsigned long)0x0037ad64)
/* dsp::TimeStretch::getStreamAt is the deck's playback stream. It wraps
   PcmReader::getStreamAt and is the speed and master-tempo stage, so its output
   is what the deck actually plays. PcmReader::getStreamAt itself is shared with
   Player::update's BPM and waveform analysis scan, which walks the whole track
   out of order; a sequential DSP cannot sit there. TimeStretch+4 is the reader,
   which identifies the deck. */
#define GET_HMI_MANAGER ((unsigned long)0x001d09b4)
#define REFRESH_GLYPH   ((unsigned long)0x001d07b0)
#define SET_BEATFX_STORAGE ((unsigned long)0x001331fc)

#define LOG_FILE  "/tmp/rx3-stems.log"
#define READY_FILE "/tmp/rx3-performance.ready"
#define RENDER_PROBE_FILE "/tmp/rx3-render-probe.log"

#define TRANSITION_FRAMES 256u

/* uif::Led::State, and the half-period of the loading indication.
   SubMiconTx::setFullColorLed lights a blinking LED while
   floor((juce::Time::currentTimeMillis() - started_at) / period) is even, so
   the period the panel is given is the half-period: 500 ms is one second on,
   one second off. The on-screen toggles reuse the same origin and formula. */
#define LED_ON    1
#define LED_BLINK 2
#define BLINK_PERIOD_MS 500u
#define RX3_DIAGNOSTIC_ONLY 0
#define RX3_PITCH_DIAGNOSTIC 1
#define BEATFX_LEFT_LAYER 0x1701u
#define XPAD_RIGHT_LAYER  0x1801u
#define HEADER_LAYER      0x0101u
#define PERFORMANCE_TAB_LAYER 0x0e01u

/* Private IDs above NS_GetImageCount() == 0x15cd. The image-info hook resolves
   only these IDs to private RGB565 records, so no Pioneer resource or cached
   DirectFB surface is overwritten. IDs 0x0d7c..0x0d84 were previously used
   here by mistake; static extraction proved that they are the live SOURCE
   Aqua/Blue/Default colour selector. */
#define TAB_IMAGE_KEY   0x1600u
#define TAB_IMAGE_STEMS 0x1601u
#define TAB_IMAGE_STATUS_NONE 0x1602u
#define TAB_IMAGE_KEY_NONE 0x1603u
#define TAB_IMAGE_BYTES 18000u
#define TAB_IMAGE_SAMPLES 0x1604u
#define TAB_IMAGE_SAMPLES_NONE 0x1605u
#define TAB_IMAGE_SAMPLES_BEATFX 0x1606u
#define TAB_IMAGE_SINGLE_KEY_NONE 0x1607u
#define TAB_IMAGE_SINGLE_KEY_SELECTED 0x1608u
#define TAB_IMAGE_SINGLE_STEMS_NONE 0x1609u
#define TAB_IMAGE_SINGLE_STEMS_SELECTED 0x160au
#define TAB_IMAGE_COUNT 11u
/* Share the STATUS / BEAT FX top border; stop touches before that lower row. */
#define CUSTOM_TAB_OFFSET_Y 21u
#define CUSTOM_TAB_TOUCH_BOTTOM 431
#define STOCK_IMAGE_COUNT 0x15cdu
/* The private ids: eleven for the tab strip, then the glyph atlas's reserve.
   This is one more than the largest id, and the guarded launch patch in
   mod/modules/core/module.sh writes that largest id into the player's
   own bound. The two move together, with tests/test_module_consistency.py
   pinning them to each other and to the image-info guard below. */
#define EXTENDED_IMAGE_COUNT 0x16a6u
#define IMAGE_TABLE_POINTER ((unsigned long)0x05a14f60)
#define TAB_KEY_PATH "/root/pdj/rx3-key-selected.rgb565"
#define TAB_STEMS_PATH "/root/pdj/rx3-stems-selected.rgb565"
#define TAB_STATUS_NONE_PATH "/root/pdj/rx3-status-none-selected.rgb565"
#define TAB_KEY_NONE_PATH "/root/pdj/rx3-none-selected.rgb565"

/* Reject a stem above this fraction of estimated available RAM. */
#define MEM_NUMERATOR   3
#define MEM_DENOMINATOR 5

/* Types and libc declarations. */

#include "api/rx3_platform.h"
#include "services/rx3_hooks.h"
#include "firmware/rx3_patch.h"
#include "services/rx3_log.h"
#include "runtime/rx3_modules.h"
#include "api/rx3_module_api.h"
#include "services/rx3_panels.h"
#include "services/rx3_images.h"
#include "services/rx3_browse.h"
#include "services/rx3_mix_state.h"

/* Data model. */

typedef struct { float left, right; } Float2;
typedef struct { int16_t left, right; } Short2;

#include "diagnostics/rx3_probe_format.h"
#include "api/rx3_feature_api.h"
#include "ui/rx3_pad_layout.h"
#include "../stems/rx3_stems_decl.h"
#include "../logo/rx3_logo_decl.h"
#include "../theme-white/rx3_theme_decl.h"
#include "../samples/rx3_samples_decl.h"
#include "../samples/rx3_samples_state.h"

typedef unsigned long (*get_stream_fn)(void *, unsigned long, Float2 *, unsigned long);
typedef int (*load_fn)(void *, const void *);
typedef int (*on_key_pad_fn)(void *, const void *);
typedef void (*check_slip_led_fn)(void *, void *);
typedef void (*hw_fill_rect_fn)(void *, const uint8_t *);
typedef int (*send_key_fn)(void *, unsigned int, unsigned int, unsigned int,
                           unsigned int, unsigned int, unsigned int);
typedef void (*set_led_color_fn)(void *, int, int, const void *);
/* uif::Led::setState(State, period_ms, started_at_ms, long, BrightnessState).
   With State 2 the panel runs the blink itself, so the rate of the LED refresh
   this hook rides on does not affect the cadence. */
typedef void (*set_led_state_fn)(void *, int, unsigned int, unsigned int, long, int);
typedef void (*draw_text_fn)(void *, void *);
typedef void (*draw_image_fn)(void *, void *);
typedef void *(*image_info_fn)(unsigned int);
typedef void (*solve_touch_fn)(void *, const void *, const void *);
typedef void *(*beatfx_xpad_ctor_fn)(void *, void *);
typedef void (*audio_start_fn)(void *, void *);
typedef int (*audio_buffer_size_fn)(void *);
typedef double (*audio_sample_rate_fn)(void *);
typedef void (*set_beatfx_selected_fn)(int);
typedef int (*get_beatfx_selected_fn)(void);

/* Expected prologues, checked before writing executable code. */
static const uint8_t load_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x5c, 0xd0, 0x4d, 0xe2
};
static const uint8_t pad_guard[8] = {
    0xb8, 0x30, 0xd1, 0xe1, 0xf0, 0x4f, 0x2d, 0xe9
};
static const uint8_t hot_cue_guard[8] = {
    0x10, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
static const uint8_t pad_mode_guard[8] = {
    0x0b, 0x30, 0xd1, 0xe5, 0x00, 0x20, 0xa0, 0xe1
};
/* This prologue contains a PC-relative ldr and requires literal relocation. */
static const uint8_t slip_led_guard[8] = {
    0xb4, 0x3d, 0x9f, 0xe5, 0xf0, 0x4f, 0x2d, 0xe9
};
static const uint8_t draw_text_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x4d, 0xdf, 0x4d, 0xe2
};
static const uint8_t draw_image_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0xcc, 0xd0, 0x4d, 0xe2
};
static const uint8_t touch_guard[8] = {
    0xf0, 0x45, 0x2d, 0xe9, 0x02, 0x60, 0xa0, 0xe1
};
static const uint8_t hw_fill_rect_guard[8] = {
    0xf0, 0x41, 0x2d, 0xe9, 0x08, 0xd0, 0x4d, 0xe2
};
static const uint8_t send_key_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x0c, 0xd0, 0x4d, 0xe2
};
static const uint8_t beatfx_xpad_ctor_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x7c, 0xd0, 0x4d, 0xe2
};
static const uint8_t audio_start_guard[8] = {
    0x00, 0x30, 0x91, 0xe5, 0xf0, 0x47, 0x2d, 0xe9
};
static const uint8_t set_beatfx_guard[8] = {
    0x98, 0x33, 0x0b, 0xe3, 0x16, 0x32, 0x40, 0xe3
};
static get_stream_fn original_get_stream;
static load_fn       original_load;
static on_key_pad_fn original_on_key_pad;
static on_key_pad_fn original_on_key_hot_cue;
static on_key_pad_fn original_on_key_beat_loop;
static on_key_pad_fn original_on_key_slip_loop;
static on_key_pad_fn original_on_key_beat_jump;
static check_slip_led_fn original_check_slip_led;
static hw_fill_rect_fn original_hw_fill_rect;
static send_key_fn original_send_key;

static volatile void *deck_readers[2];
static volatile int state_thread_running;
static pthread_t state_thread;
static int state_thread_started;
static volatile uint64_t overlay_seen_us;
static volatile uint64_t overlay_drawn_us;
static volatile unsigned int captured_touch;
static unsigned int captured_touch_deck;
static volatile unsigned int overlay_panel;
static volatile unsigned int native_beatfx_selected;
static volatile unsigned long draw_calls;
static volatile unsigned long main_window_draws;
static volatile unsigned long image_draw_calls;
static volatile unsigned long custom_tab_draws;
static volatile unsigned long custom_pad_draws;
static volatile unsigned long touch_calls;
/* The render probe. The counters above say how much was drawn; the probe says
   what. One line per distinct draw, held in memory and written out by the
   watcher, because a draw hook that opens a file runs on the render thread. */
static int render_probe_enabled;
#define PROBE_SEEN_MAX   1024u
#define PROBE_RING_BYTES 16384u
/* Three words identify a draw: a tagged layer, and two fields off the object. */
static unsigned int probe_seen[PROBE_SEEN_MAX][3];
static unsigned int probe_seen_count;
static char probe_ring[PROBE_RING_BYTES];
static unsigned int probe_ring_used;
static volatile unsigned int stock_tab_backing_ready;
static uint8_t stock_tab_backing[0x54];
static volatile unsigned int tab_assets_ready;
static volatile unsigned int tab_assets_installing;
/* The watcher holds the private image table back until this microsecond, so an
   operator can watch the stock tabs draw first and see which route installs.
   Zero means no delay, which is the ordinary case. */
static uint64_t tab_install_not_before_us;
static volatile unsigned int initial_performance_refresh_done;
static volatile unsigned long audio_start_calls;
static volatile uint8_t performance_window;
static volatile unsigned int performance_window_ready;
static volatile unsigned int text_template_ready;
static uint8_t text_template[0x54];
/* 0 none, 1 a plausible label, 2 a label that also carries a fill. */
static volatile unsigned int pad_text_template_ready;
static uint8_t pad_text_template[0x54];

struct touch_geometry {
    int x;
    int y;
    unsigned int width;
    unsigned int height;
};

static void *beatfx_touch_areas[6];
static struct touch_geometry stock_touch_geometry[6];
/* Which control is held, so the row can paint it pressed. -1 is nothing. */
static void *performance_left_glyph;
static void *performance_right_glyph;
static void *key_tab_glyph;
static void *stems_tab_glyph;
static void *stock_status_glyph;
static volatile unsigned int beatfx_reselect_generation;
static volatile unsigned int beatfx_reselect_pending;

static const struct rx3_pad_row *row_for_id(unsigned int panel_id);
static int deck_index_for_reader(const void *reader);

static int stems_feature_configured(void);
static int stems_feature_install(void);
static void stems_feature_remove(void);
static void stems_feature_track_will_load(unsigned int deck, void *reader,
                                          const void *track_info);
static void stems_feature_track_did_load(unsigned int deck, void *reader,
                                         const void *track_info);
static void stems_feature_destroy_deck(unsigned int deck);
static const struct rx3_pad_row stems_row;
static const struct rx3_pad_row samples_row;
static int hooked_on_key_pad(void *, const void *);
static int samples_enter_mode(void);
static void samples_leave_mode(void);
static void samples_shift_pressed(void);
static volatile unsigned int pad_callbacks_active;
static int theme_feature_configured(void);
static int theme_feature_install(void);
static void theme_feature_remove(void);
static void theme_run_pending_toggle(void);
static void theme_remap_image(unsigned int image);
static void utility_poll_theme_row(void);
static uint8_t *theme_stock_table;
static void theme_build_light_table(uint8_t *dark_table);
static unsigned long memory_available_kb(void);
static int samples_feature_configured(void);
static int samples_feature_install(void);
static void samples_feature_remove(void);

#define RUNTIME_FEATURE_COUNT 3u

static struct rx3_runtime_feature runtime_features[RUNTIME_FEATURE_COUNT] = {
    {
        "stems", 0, &stems_row,
        stems_feature_configured, stems_feature_install,
        stems_feature_remove, stems_feature_track_will_load,
        stems_feature_track_did_load, 0, 0, stems_feature_destroy_deck
    },
    {
        /* No panel and no per-deck state: the theme is a property of the
           whole interface, not of a deck. */
        "theme-white", 0, 0,
        theme_feature_configured, theme_feature_install,
        theme_feature_remove, 0, 0, 0, 0, 0
    },
    {
        "samples", 0, &samples_row,
        samples_feature_configured, samples_feature_install,
        samples_feature_remove, 0, 0, 0, 0, 0
    },
};

static struct installed_hook get_stream_hook;
static struct installed_hook load_hook;
static struct installed_hook pad_hook;
static struct installed_hook hot_cue_hook;
static struct installed_hook beat_loop_hook;
static struct installed_hook physical_pad_mode_hook;
static on_key_pad_fn original_on_physical_key;
static struct installed_hook slip_loop_hook;
static struct installed_hook beat_jump_hook;
static struct installed_hook slip_led_hook;
static struct installed_hook draw_text_hook;
static struct installed_hook draw_image_hook;
static struct installed_hook image_info_hook;
static struct installed_hook hw_fill_rect_hook;
static struct installed_hook send_key_hook;
static struct installed_hook touch_hook;
static struct installed_hook beatfx_xpad_ctor_hook;
static struct installed_hook audio_start_hook;
static struct installed_hook set_beatfx_hook;
static draw_text_fn original_draw_text;
static draw_image_fn original_draw_image;
static image_info_fn original_image_info;
static solve_touch_fn original_solve_touch;
static beatfx_xpad_ctor_fn original_beatfx_xpad_ctor;
static audio_start_fn original_audio_start;
static set_beatfx_selected_fn original_set_beatfx_selected;
/* Logging. */

static size_t str_length(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

static void log_number(const char *label, unsigned long value)
{
    char buffer[96];
    size_t n = 0;
    while (label[n] && n < sizeof(buffer) - 24) {
        buffer[n] = label[n];
        n++;
    }
    char digits[24];
    int d = 0;
    if (!value) {
        digits[d++] = '0';
    } else {
        while (value && d < (int)sizeof(digits)) {
            digits[d++] = (char)('0' + (value % 10u));
            value /= 10u;
        }
    }
    while (d > 0)
        buffer[n++] = digits[--d];
    buffer[n] = '\0';
    log_line(buffer);
}

/* A drawable's layer, and the two object fields that separate one draw from
   another within a layer. Read here so the two record builders below agree. */
#define PROBE_LAYER_OFFSET  0x10u
#define PROBE_FIRST_OFFSET  0x28u
#define PROBE_SECOND_OFFSET 0x44u
#define PROBE_STYLE_OFFSET  0x38u
/* Text and images share one table, so the text side tags its key. */
#define PROBE_TEXT_TAG      0x10000u

static unsigned int probe_word(const void *object, unsigned int offset)
{
    unsigned int value;
    memcpy(&value, (const uint8_t *)object + offset, sizeof(value));
    return value;
}

static unsigned int probe_layer(const void *object)
{
    uint16_t value;
    memcpy(&value, (const uint8_t *)object + PROBE_LAYER_OFFSET, sizeof(value));
    return value;
}

/* Answers whether this draw has been recorded before. Once the table is full it
   stops growing and every unmatched draw records again, which is the reference's
   behaviour and is itself the signal that the run has more shapes than fit. */
static int probe_first_time(unsigned int key, unsigned int first, unsigned int second)
{
    for (unsigned int i = 0; i < probe_seen_count; i++)
        if (probe_seen[i][0] == key && probe_seen[i][1] == first &&
            probe_seen[i][2] == second)
            return 0;
    if (probe_seen_count < PROBE_SEEN_MAX) {
        probe_seen[probe_seen_count][0] = key;
        probe_seen[probe_seen_count][1] = first;
        probe_seen[probe_seen_count][2] = second;
        probe_seen_count++;
    }
    return 1;
}

/* A line that does not fit is dropped rather than truncated: half a rectangle
   reads as a rectangle. The ring stops growing until the watcher drains it. */
static void probe_append(const char *start, const char *end)
{
    unsigned int length = (unsigned int)(end - start);
    if (probe_ring_used + length + 1u > PROBE_RING_BYTES)
        return;
    if (length)
        memcpy(probe_ring + probe_ring_used, start, length);
    probe_ring[probe_ring_used + length] = '\n';
    probe_ring_used += length + 1u;
}

/* Worst case is the text record: two tag bytes, three hex words, a rectangle of
   four decimals, and one more decimal, with a separator between each. */
#define PROBE_RECORD_BYTES 128u

static void probe_record_image(const void *image)
{
    unsigned int layer = probe_layer(image);
    unsigned int second = probe_word(image, PROBE_SECOND_OFFSET);
    if (!probe_first_time(layer, second, 0u))
        return;
    char record[PROBE_RECORD_BYTES];
    char *out = record;
    *out++ = 'I';
    *out++ = ' ';
    out = probe_put_hex(out, layer);
    *out++ = ' ';
    out = probe_put_hex(out, second);
    *out++ = ' ';
    out = probe_put_rect(out, image);
    probe_append(record, out);
}

static void probe_record_text(const void *text)
{
    unsigned int layer = probe_layer(text);
    unsigned int first = probe_word(text, PROBE_FIRST_OFFSET);
    unsigned int second = probe_word(text, PROBE_SECOND_OFFSET);
    unsigned int style = ((const uint8_t *)text)[PROBE_STYLE_OFFSET];
    if (!probe_first_time(layer | PROBE_TEXT_TAG, first, second | (style << 24)))
        return;
    char record[PROBE_RECORD_BYTES];
    char *out = record;
    *out++ = 'T';
    *out++ = ' ';
    out = probe_put_hex(out, layer);
    *out++ = ' ';
    out = probe_put_hex(out, first);
    *out++ = ' ';
    out = probe_put_hex(out, second);
    *out++ = ' ';
    out = probe_put_rect(out, text);
    *out++ = ' ';
    out = probe_put_dec(out, style);
    probe_append(record, out);
}

/* Called from the watcher, never from a draw hook: this opens a file. */
static void probe_flush(void)
{
    if (!probe_ring_used)
        return;
    int fd = open(RENDER_PROBE_FILE, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd < 0)
        return;
    (void)write(fd, probe_ring, probe_ring_used);
    close(fd);
    probe_ring_used = 0;
}








struct rx3_timeval { long seconds, microseconds; };

static uint64_t monotonic_enough_us(void)
{
    struct rx3_timeval value;
    if (gettimeofday(&value, 0))
        return 0;
    return (uint64_t)(unsigned long)value.seconds * 1000000u +
           (uint64_t)(unsigned long)value.microseconds;
}

/* juce::Time::currentTimeMillis, which the panel compares the LED blink
   against, is gettimeofday reduced to milliseconds. Reproducing it here keeps
   the on-screen toggles in the LED's own time domain. */
static unsigned int now_ms(void)
{
    return (unsigned int)(monotonic_enough_us() / 1000u);
}

static int deck_is_loading(const struct stems_deck_context *context)
{
    return context->reader && context->armed && !context->payloads[0].data;
}

static int any_deck_is_loading(void)
{
    return deck_is_loading(&stems_decks[0]) ||
           deck_is_loading(&stems_decks[1]);
}

/* One origin for both indications: the pads run their blink in the panel, the
   toggles are redrawn from the same parity, so the two cannot drift apart. */
static unsigned int blink_origin_ms(void)
{
    if (!blink_origin_valid) {
        blink_origin = now_ms();
        blink_origin_valid = 1u;
    }
    return blink_origin;
}

static int blink_phase_is_on(void)
{
    return (((now_ms() - blink_origin_ms()) / BLINK_PERIOD_MS) & 1u) == 0u;
}

static void refresh_performance_ui(void);
static int read_exactly(int fd, void *destination, size_t length);

static uint8_t tab_image_pixels[TAB_IMAGE_COUNT][TAB_IMAGE_BYTES];
static uint8_t light_tab_image_pixels[TAB_IMAGE_COUNT][TAB_IMAGE_BYTES];
static unsigned int light_tab_assets_ready;
static unsigned int tab_asset_attempts;
/* A refresh asks the player to repaint five glyphs, once. One repaint loses a
   race the player starts on its own: it redraws the stock row from a path of
   its own, our controls go with it, and nothing asks a second time, so a
   change made at the wrong moment flickers and reverts. Holding a deadline
   repeats the request for as long as the window lasts.

   The repeat is throttled rather than run on every intercepted draw. Painting
   the row once per draw was measured at 331 paints where 6 were wanted, so the
   window costs about eleven repaints instead of one, and not three hundred. */
static volatile unsigned int performance_refresh_pending;
#define PERFORMANCE_REFRESH_WINDOW_US 1000000u
#define PERFORMANCE_REFRESH_EVERY_US   100000u
static uint64_t performance_refresh_until_us;
static uint64_t performance_refresh_next_us;
static unsigned int performance_refresh_reported;

#include "ui/rx3_pad_atlas.h"
#include "firmware/rx3_message.h"

static void install_logo_record(uint8_t *table);

static void install_tab_assets(const char *route)
{
    if (tab_assets_ready)
        return;
    if (!__sync_bool_compare_and_swap(&tab_assets_installing, 0u, 1u))
        return;
    static const char *paths[TAB_IMAGE_COUNT] = {
        TAB_KEY_PATH,
        TAB_STEMS_PATH,
        TAB_STATUS_NONE_PATH,
        TAB_KEY_NONE_PATH,
        "/root/pdj/rx3-samples-selected.rgb565",
        "/root/pdj/rx3-samples-none-selected.rgb565",
        "/root/pdj/rx3-samples-beatfx-selected.rgb565",
        "/root/pdj/rx3-single-key-none.rgb565",
        "/root/pdj/rx3-single-key-selected.rgb565",
        "/root/pdj/rx3-single-stems-none.rgb565",
        "/root/pdj/rx3-single-stems-selected.rgb565"
    };

    for (unsigned int i = 0; i < TAB_IMAGE_COUNT; i++) {
        int fd = open(paths[i], O_RDONLY);
        if (fd < 0 || read_exactly(fd, tab_image_pixels[i],
                                  TAB_IMAGE_BYTES)) {
            if (fd >= 0)
                close(fd);
            log_line("warning: custom tab bitmap installation failed");
            tab_assets_installing = 0u;
            return;
        }
        close(fd);
    }

    static const char *light_paths[TAB_IMAGE_COUNT] = {
        "/root/pdj/rx3-key-selected-light.rgb565",
        "/root/pdj/rx3-stems-selected-light.rgb565",
        "/root/pdj/rx3-status-none-selected-light.rgb565",
        "/root/pdj/rx3-none-selected-light.rgb565",
        "/root/pdj/rx3-samples-selected-light.rgb565",
        "/root/pdj/rx3-samples-none-selected-light.rgb565",
        "/root/pdj/rx3-samples-beatfx-selected-light.rgb565",
        "/root/pdj/rx3-single-key-none-light.rgb565",
        "/root/pdj/rx3-single-key-selected-light.rgb565",
        "/root/pdj/rx3-single-stems-none-light.rgb565",
        "/root/pdj/rx3-single-stems-selected-light.rgb565"
    };
    light_tab_assets_ready = 1u;
    for (unsigned int i = 0; i < TAB_IMAGE_COUNT; i++) {
        int fd = open(light_paths[i], O_RDONLY);
        if (fd < 0 || read_exactly(fd, light_tab_image_pixels[i], TAB_IMAGE_BYTES))
            light_tab_assets_ready = 0u;
        if (fd >= 0) close(fd);
    }

    pad_atlas_load();

    uint8_t *stock_table = *(uint8_t **)IMAGE_TABLE_POINTER;
    if (!stock_table) {
        tab_assets_installing = 0u;
        return;
    }
    theme_stock_table = stock_table;
    size_t table_bytes = EXTENDED_IMAGE_COUNT * 44u;
    uint8_t *table = mmap(0, table_bytes, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (table == MAP_FAILED) {
        log_line("warning: private image table allocation failed");
        tab_assets_installing = 0u;
        return;
    }
    memcpy(table, stock_table, STOCK_IMAGE_COUNT * 44u);

    /* Stock records keep their pixel payloads in rbp's original allocation.
       Convert each relative offset so resolving it against the secondary
       table reaches the same original address. */
    uint32_t relocation = (uint32_t)(unsigned long)stock_table -
                          (uint32_t)(unsigned long)table;
    for (unsigned int image = 0; image < STOCK_IMAGE_COUNT; image++) {
        uint8_t *record = table + image * 44u;
        uint32_t data_offset;
        memcpy(&data_offset, record + 0x20u, sizeof(data_offset));
        data_offset += relocation;
        memcpy(record + 0x20u, &data_offset, sizeof(data_offset));
        if (record[0x19u]) {
            uint32_t palette_offset;
            memcpy(&palette_offset, record + 0x24u,
                   sizeof(palette_offset));
            palette_offset += relocation;
            memcpy(record + 0x24u, &palette_offset,
                   sizeof(palette_offset));
        }
    }

    for (unsigned int i = 0; i < TAB_IMAGE_COUNT; i++) {
        uint8_t *record = table + (TAB_IMAGE_KEY + i) * 44u;
        memcpy(record, table + 0x1598u * 44u, 44u);
        uint16_t width = 180u;
        uint16_t height = 50u;
        uint32_t pixels = (uint32_t)(unsigned long)tab_image_pixels[i] -
                          (uint32_t)(unsigned long)table;
        uint32_t no_palette = 0u;
        memcpy(record + 4u, &width, sizeof(width));
        memcpy(record + 6u, &height, sizeof(height));
        record[0x18u] = 1u; /* RGB565 */
        record[0x19u] = 0u;
        memcpy(record + 0x20u, &pixels, sizeof(pixels));
        memcpy(record + 0x24u, &no_palette, sizeof(no_palette));
    }

    if (pad_atlas_ready)
        pad_atlas_install_records(table, pad_atlas_blob);

    install_logo_record(table);
    /* The light interface is built from the finished table, so it inherits the
       logo and the tab assets rather than needing its own copies of them. */
    theme_build_light_table(table);

    __sync_synchronize();
    *(uint8_t **)IMAGE_TABLE_POINTER = table;
    __sync_synchronize();
    tab_assets_ready = 1u;
    /* Released on the way out as it is on every failure path. The ready latch
       above already turns later callers away, so holding the claim changed
       nothing; a flag that is only ever true after a success says the wrong
       thing to whoever adds the next route. */
    tab_assets_installing = 0u;
    log_line("extended private KEY/STEMS image table installed");
    log_line(route);
}

static void *watch_patch_state(void *unused)
{
    (void)unused;
    unsigned int ticks = 0;
    int last_phase = -1;
    while (__atomic_load_n(&state_thread_running, __ATOMIC_SEQ_CST)) {
        usleep(50000u);
        utility_poll_theme_row();
        if (ticks % 10u == 0u) (void)rx3_message_allowed();
        if (!tab_assets_ready &&
            (!tab_install_not_before_us ||
             monotonic_enough_us() >= tab_install_not_before_us))
            install_tab_assets("image table route: watcher thread");
        if (render_probe_enabled)
            probe_flush();
        if (theme_global_dark) {
            int sentinel = open(THEME_DARK_SENTINEL, O_RDONLY);
            if (sentinel >= 0) {
                close(sentinel);
                theme_global_dark = 0;
                log_line("theme: rx3-theme.off seen, global remap stopped");
            }
        }
        /* Nothing else invalidates the pad windows while a stem is read, so
           the blink has to ask for the redraw that carries its own parity. */
        const struct rx3_pad_row *row = row_for_id(overlay_panel);
        if (row && row->needs_refresh && row->needs_refresh() &&
            performance_window_ready) {
            int phase = blink_phase_is_on();
            if (overlay_panel != 2u || !any_deck_is_loading() || phase != last_phase) {
                last_phase = phase;
                __atomic_store_n(&performance_refresh_pending, 1u, __ATOMIC_SEQ_CST);
            }
        } else {
            last_phase = -1;
            if (!any_deck_is_loading())
                blink_origin_valid = 0u;
        }
        ticks++;
        if (RX3_PITCH_DIAGNOSTIC && ticks % 100u == 0u)
            for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++)
                if (runtime_features[i].active && runtime_features[i].report)
                    runtime_features[i].report();
        if (RX3_PITCH_DIAGNOSTIC && ticks % 100u == 0u)
            rx3_modules_report();
        if (ticks == 100u) {
            log_number("probe text draw calls = ", draw_calls);
            log_number("probe main-window draws = ", main_window_draws);
            log_number("probe image draw calls = ", image_draw_calls);
            log_number("probe custom tab draws = ", custom_tab_draws);
            log_number("probe custom PAD draws = ", custom_pad_draws);
            log_number("probe touch calls = ", touch_calls);
            log_number("probe audio-start calls = ", audio_start_calls);
        }
    }
    return 0;
}

static unsigned int self_pid(void)
{
    char stat[16];
    int fd = open("/proc/self/stat", O_RDONLY);
    if (fd < 0) return 0;
    ssize_t count = read(fd, stat, sizeof(stat));
    close(fd);
    if (count < 2) return 0;
    unsigned int pid = 0;
    for (ssize_t i = 0; i < count; i++) {
        if (stat[i] == ' ') return pid;
        if (stat[i] < '0' || stat[i] > '9') return 0;
        pid = pid * 10u + (unsigned int)(stat[i] - '0');
    }
    return 0;
}

static void publish_ready(void)
{
    unsigned int value = self_pid();
    if (!value) return;
    int fd = open(READY_FILE, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0)
        return;
    /* Bind readiness to this process. A marker left by an earlier rbp must
       never be accepted as proof that the current process installed hooks. */
    char digits[16];
    unsigned int length = 0;
    do {
        digits[length++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value && length < sizeof(digits) - 1u);
    char marker[16];
    for (unsigned int i = 0; i < length; i++)
        marker[i] = digits[length - i - 1u];
    marker[length++] = '\n';
    (void)write(fd, marker, length);
    close(fd);
}

/* Stem loading. */

/* Estimate immediately available or reclaimable RAM in KiB. */
static unsigned long meminfo_value(const char *buffer, ssize_t count,
                                   const char *key)
{
    size_t key_length = str_length(key);
    for (ssize_t i = 0; i + (ssize_t)key_length < count; i++) {
        if (memcmp(buffer + i, key, key_length))
            continue;
        ssize_t j = i + (ssize_t)key_length;
        while (j < count && (buffer[j] == ' ' || buffer[j] == '\t'))
            j++;
        unsigned long value = 0;
        while (j < count && buffer[j] >= '0' && buffer[j] <= '9')
            value = value * 10u + (unsigned long)(buffer[j++] - '0');
        return value;
    }
    return 0;
}

static unsigned long memory_available_kb(void)
{
    char buffer[2048];
    int fd = open("/proc/meminfo", O_RDONLY);
    if (fd < 0)
        return 0;
    ssize_t count = read(fd, buffer, sizeof(buffer) - 1);
    close(fd);
    if (count <= 0)
        return 0;
    buffer[count] = '\0';

    /* Linux 3.0.101 has no MemAvailable field. Fall back to a conservative
       estimate from free, buffer, and cache pages. */
    unsigned long available = meminfo_value(buffer, count, "MemAvailable:");
    if (available)
        return available;
    return meminfo_value(buffer, count, "MemFree:") +
           meminfo_value(buffer, count, "Buffers:") +
           meminfo_value(buffer, count, "Cached:");
}

static int read_exactly(int fd, void *destination, size_t length)
{
    uint8_t *cursor = destination;
    while (length) {
        ssize_t got = read(fd, cursor, length > 0x100000u ? 0x100000u : length);
        if (got <= 0)
            return -1;
        cursor += got;
        length -= (size_t)got;
    }
    return 0;
}

static void release_payload(struct stem_payload *payload)
{
    if (payload->block)
        munmap(payload->block, payload->block_size);
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

/* Hook installation. */

/* Native overlay. NS_PALRender_DrawText receives a fully attached 0x54-byte
   NS_GlyphText. Clone a stock label from the pane the row stands in for, retain
   its window/parent, and alter only the public text-box fields established by
   NS_GlyphText_CreateFromProperty. Cloning is what carries the font: nothing
   below sets one, so the controls wear whichever face the model was drawn in. */

static const uint16_t text_empty[]    = {0};

static const struct rx3_pad_row *row_for_id(unsigned int panel_id)
{
    return rx3_panel_find(panel_id);
}

static const struct rx3_pad_row *row_for_slot(unsigned int slot)
{
    return rx3_panel_find(slot + 1u);
}

static void set_u16(void *object, unsigned int offset, uint16_t value)
{
    memcpy((uint8_t *)object + offset, &value, sizeof(value));
}

static void set_u32(void *object, unsigned int offset, uint32_t value)
{
    memcpy((uint8_t *)object + offset, &value, sizeof(value));
}

/* Native surface fills use one byte per component, at 5/6/5 precision. */
static uint32_t pad_native_fill_colour(uint32_t rgb888)
{
    return ((rgb888 >> 19) & 31u) | (((rgb888 >> 10) & 63u) << 8) |
           (((rgb888 >> 3) & 31u) << 16);
}

static void draw_native_box_local(void *render, const void *model,
                                  const void *window_model,
                                  uint8_t target_window,
                                  int x1, int y1, int x2, int y2,
                                  const uint16_t *label,
                                  uint32_t foreground, uint32_t background)
{
    /* NS_PALRender_DrawText packs a 16-bit pixel for these windows, but
       DS_HW_Core_Surface_FillRectangle consumes three separate 5/6/5 bytes.
       Use the same native window/position and rectangle API directly. This
       avoids losing blue and folding its bits into green (rbp 1.19). */
    (void)render; (void)model; (void)label; (void)foreground;
    static int checked, supported;
    if (!checked) {
        static const uint32_t fill_guard[2] = {0xe92d4030u, 0xe24dd014u};
        static const uint32_t colour_guard[2] = {0xe59f3140u, 0xe92d4030u};
        static const uint32_t position_guard[2] = {0xe30831d0u, 0xe3403249u};
        supported = !memcmp((const void *)0x001a245cu,fill_guard,8) &&
                    !memcmp((const void *)0x001a0680u,colour_guard,8) &&
                    !memcmp((const void *)0x001d46f0u,position_guard,8);
        checked = 1;
        if (!supported) log_line("pad fill disabled: unexpected native drawing ABI");
    }
    if (!supported) return;
    uint16_t window_layer;
    memcpy(&window_layer,(const uint8_t *)window_model+0x10u,2);
    unsigned int index = ((unsigned int)target_window << 8) | (window_layer >> 8);
    void *window = ((void **)0x05a15f68u)[index];
    if (!window) return;
    int origin_x=0, origin_y=0;
    ((void (*)(int *,int *))0x001d46f0u)(&origin_x,&origin_y);
    uint32_t colour = pad_native_fill_colour(background);
    ((int (*)(void *,unsigned int,uint32_t))0x001a0680u)(window,1u,colour);
    uint32_t size = (uint32_t)(x2-x1+1) | ((uint32_t)(y2-y1+1) << 16);
    ((int (*)(void *,int,int,uint32_t))0x001a245cu)(window,origin_x+x1,origin_y+y1,size);
}

/* The same clone, for artwork rather than a string.
 *
 * An image draw carries its id in the field a text draw uses for a background,
 * and the box places it: draw_custom_tabs has been putting a 180x50 tab on
 * screen this way since the tab strip was first replaced. The model to clone is
 * the pane backdrop the row is painted from, which is already attached to the
 * right renderer, window and subtree. */
static void draw_native_image_local(void *render, const void *model,
                                    uint8_t target_window,
                                    int x1, int y1, int x2, int y2,
                                    uint32_t image_id)
{
    uint8_t box[0x54];
    uint16_t window_layer;
    memcpy(box, model, sizeof(box));
    memcpy(&window_layer, (const uint8_t *)model + 0x10u, sizeof(window_layer));
    window_layer = (uint16_t)((window_layer & 0xff00u) | target_window);
    set_u16(box, 0x10, window_layer);
    set_u16(box, 0x18, (uint16_t)x1);
    set_u16(box, 0x1a, (uint16_t)y1);
    set_u16(box, 0x1c, (uint16_t)x2);
    set_u16(box, 0x1e, (uint16_t)y2);
    set_u32(box, 0x44, image_id);
    original_draw_image(render, box);
}

/* Compatibility marker for the pad-fill call; captions use the glyph atlas. */
#define PAD_COLOUR_INHERIT  0x00000000u

static void refresh_initial_performance_tabs_if_ready(void)
{
    /* REFRESH_GLYPH must run from rbp's UI rendering path. Calling it from the
       state watcher can stall the renderer during startup. Every caller sets
       or captures a native glyph immediately before reaching this guard. */
    if (!initial_performance_refresh_done && tab_assets_ready &&
        text_template_ready && stock_tab_backing_ready &&
        key_tab_glyph && stems_tab_glyph && stock_status_glyph) {
        initial_performance_refresh_done = 1u;
        refresh_performance_ui();
        log_line("initial native performance tabs refreshed");
        /* The player is back and drawing; the loaders are not finished. This is
           the wait the operator is actually living through, and the first thing
           the mod has ever had a way to say. */
        rx3_message_show(0u, &message_drive_loading);
    }
}

static uint32_t performance_tab_image(const struct rx3_pad_row *left,
                                      const struct rx3_pad_row *right,
                                      unsigned int panel)
{
    if (!left && !right) return 0u;
    if (left && right) {
        const struct rx3_pad_row *active = panel == left->panel_id ? left :
                                           panel == right->panel_id ? right : 0;
        return active ? active->tab_image : TAB_IMAGE_KEY_NONE;
    }
    if (left) return panel == left->panel_id ?
                     TAB_IMAGE_SINGLE_KEY_SELECTED : TAB_IMAGE_SINGLE_KEY_NONE;
    return panel == right->panel_id ?
           TAB_IMAGE_SINGLE_STEMS_SELECTED : TAB_IMAGE_SINGLE_STEMS_NONE;
}

static uint32_t performance_status_image(unsigned int samples,
                                         unsigned int panel,
                                         uint32_t native_image)
{
    if (!samples) return panel ? TAB_IMAGE_STATUS_NONE : native_image;
    if (panel == 3u) return TAB_IMAGE_SAMPLES;
    if (!panel && native_image == 0x1598u) return TAB_IMAGE_SAMPLES_BEATFX;
    return TAB_IMAGE_SAMPLES_NONE;
}


/* The tab strip. The stock STATUS / BEAT FX row is captured as it goes past --
   see the image id below -- and redrawn at the KEY / STEMS position, so the
   frame, the corner radius and the palette are rbp's own rather than a
   reconstruction. Drawing the boxes by hand was tried and rejected: the theme
   colours are not exposed, and every literal guess looked foreign. */
static void draw_custom_tabs(void *render, const void *image)
{
    overlay_seen_us = monotonic_enough_us();
    const struct rx3_pad_row *left = row_for_slot(0u);
    const struct rx3_pad_row *right = row_for_slot(1u);
    uint32_t tab_image = performance_tab_image(left,right,overlay_panel);
    if (!stock_tab_backing_ready || !tab_image) {
        original_draw_image(render, (void *)image);
        return;
    }
    uint16_t window_layer;
    memcpy(&window_layer, (const uint8_t *)image + 0x10u, sizeof(window_layer));

    uint8_t backing[0x54];
    memcpy(backing, stock_tab_backing, sizeof(backing));
    if (tab_assets_ready) set_u32(backing, 0x44, tab_image);
    set_u16(backing, 0x10, window_layer);
    set_u16(backing, 0x18, 10u);
    set_u16(backing, 0x1a, CUSTOM_TAB_OFFSET_Y);
    set_u16(backing, 0x1c, 190u);
    set_u16(backing, 0x1e, 50u + CUSTOM_TAB_OFFSET_Y);
    original_draw_image(render, backing);
    custom_tab_draws++;
}

/* The model a filled box is cut from.
 *
 * It no longer carries the row's typeface: the lettering is artwork now, and
 * nothing about a cloned text object ever selected a face anyway. What is left
 * is a model with the right renderer and window attachment to place a
 * rectangle with, so either template will do, and neither being captured yet
 * means there is nothing to cut from and the caller says so. */
static const void *pad_button_face(void)
{
    if (pad_text_template_ready)
        return pad_text_template;
    return text_template_ready ? text_template : 0;
}

#include "ui/rx3_pad_widgets.h"

/* Remaining legacy panel clients. Standalone modules register their rows. */
#include "../stems/rx3_stems_panel.h"
#include "../samples/rx3_samples_panel.h"

static void draw_custom_pad_half(void *render, const void *model,
                                 uint8_t window, unsigned int deck)
{
    const struct rx3_pad_row *row = row_for_id(overlay_panel);
    if (!row)
        return;
    custom_pad_draws++;
    /* The light fill hook would repaint the ground under everything drawn
       here, so it stands down for the length of the row. */
    theme_suspend_fill = 1;
    pad_row_paint(render, model, window, deck, row);
    theme_suspend_fill = 0;
}



/* The row's own subtree. The low byte of a window-layer is the deck's window,
   which decks 1 and 2 share with their info strips; the high byte names the
   widget subtree, which is what "the pads" actually means. Keying on the low
   byte swallowed AUTO CUE, QUANTIZE and the tempo badges along with the pads. */
static int is_performance_pad_subtree(uint16_t window_layer)
{
    unsigned int subtree = (unsigned int)(window_layer >> 8);
    return subtree == 0x17u || subtree == 0x18u;
}

static unsigned int deck_for_pad_subtree(uint16_t window_layer)
{
    return (unsigned int)(window_layer >> 8) == 0x17u ? 0u : 1u;
}

/* Clone a stock label from that subtree so the controls inherit the row's font,
   padding and clipping. Take the first plausible label, then upgrade once to
   one that also carries a fill, which is a real button rather than a caption.
   Capturing before the interception below is what makes this work at all: the
   draws worth cloning are exactly the ones a live panel replaces. */
/* Which subtree to clone the control face from.
   The pad subtree draws no text at all -- measured: twelve subtrees issue text
   draws and 0x17/0x18 are not among them, because that row is images. So there
   is no stock pad label to clone and the donor has to be chosen from elsewhere.
   0 keeps the original behaviour of waiting for a pad label that never comes.
   The knob that let an emulator try other subtrees, and the one that widened
   the height search below, left with the emulator; a deck never set either. */
static unsigned int font_donor_subtree(void)
{
    return 0u;
}

/* Selecting a donor by layer picked four faces that all render at 19 px,
   because a layer draws text at more than one size. Selecting by measured box
   height searches the actual range instead. */
static int font_donor_max_height(void)
{
    return 64;
}

static void capture_pad_text_template(const void *text, uint16_t window_layer)
{
    unsigned int donor = font_donor_subtree();
    if (pad_text_template_ready >= 2u)
        return;
    if (donor ? ((unsigned int)(window_layer >> 8) != donor)
              : !is_performance_pad_subtree(window_layer))
        return;
    if (((const uint8_t *)text)[0x38] == 0u)
        return;
    uint16_t y1, y2;
    memcpy(&y1, (const uint8_t *)text + 0x1au, sizeof(y1));
    memcpy(&y2, (const uint8_t *)text + 0x1eu, sizeof(y2));
    int height = (int)y2 - (int)y1;
    if (height < 8 || height > font_donor_max_height())
        return;
    uint32_t background;
    memcpy(&background, (const uint8_t *)text + 0x44u, sizeof(background));
    unsigned int level = background ? 2u : 1u;
    if (level <= pad_text_template_ready)
        return;
    memcpy(pad_text_template, text, sizeof(pad_text_template));
    pad_text_template_ready = level;
    log_number("pad label template captured, level = ", level);
    log_number("  donor layer = ", (unsigned long)window_layer);
    log_number("  donor box height = ", (unsigned long)height);
}

static void *hooked_image_info(unsigned int image_id)
{
    if (!tab_assets_ready && tab_asset_attempts < 8u) {
        if (*(uint8_t **)IMAGE_TABLE_POINTER)
            tab_asset_attempts++;
        install_tab_assets("image table route: image lookup hook");
    }
    void *variant=rx3_image_resolve(image_id,original_image_info,*(void **)IMAGE_TABLE_POINTER);
    return variant ? variant : original_image_info(image_id);
}

static void select_custom_panel(unsigned int panel);

static void run_pending_ui(void)
{
    unsigned int requested_panel = rx3_panel_take_open();
    if (requested_panel) select_custom_panel(requested_panel);
    if (__atomic_exchange_n(&performance_refresh_pending, 0u, __ATOMIC_SEQ_CST)) {
        uint64_t now = monotonic_enough_us();
        performance_refresh_until_us = now + PERFORMANCE_REFRESH_WINDOW_US;
        performance_refresh_next_us = now + PERFORMANCE_REFRESH_EVERY_US;
        refresh_performance_ui();
    } else if (performance_refresh_until_us) {
        uint64_t now = monotonic_enough_us();
        if (now > performance_refresh_until_us) {
            performance_refresh_until_us = 0;
            if (render_probe_enabled && !performance_refresh_reported) {
                performance_refresh_reported = 1u;
                log_line("probe: the performance row held its refresh window");
            }
        } else if (now >= performance_refresh_next_us) {
            performance_refresh_next_us = now + PERFORMANCE_REFRESH_EVERY_US;
            refresh_performance_ui();
        }
    }
    rx3_message_run_pending();
}

static void hooked_draw_image(void *render, void *image)
{
    image_draw_calls++;
    if (render_probe_enabled)
        probe_record_image(image);
    if (RX3_DIAGNOSTIC_ONLY) {
        original_draw_image(render, image);
        return;
    }
    run_pending_ui();
    /* Populate the private image records before their first DirectFB lookup.
       Pioneer image-table records and their cached surfaces stay untouched. */
    if (!tab_assets_ready)
        install_tab_assets("image table route: image draw hook");
    /* The image models can all be captured before the watcher finishes
       installing the replacement payloads. Re-check on every ordinary image
       draw so the first draw after installation performs the one-shot refresh
       on rbp's UI thread. Limiting this guard to the capture branches made the
       bootstrap dependent on draw ordering and could leave ZOOM/GRID visible
       until another native invalidation. */
    refresh_initial_performance_tabs_if_ready();
    uint16_t window_layer;
    memcpy(&window_layer, (const uint8_t *)image + 0x10u,
           sizeof(window_layer));
    uint8_t window = (uint8_t)(window_layer & 0xffu);
    uint32_t image_id;
    memcpy(&image_id, (const uint8_t *)image + 0x44u, sizeof(image_id));
    theme_remap_image(image_id);

    /* Capture the native 180x50 model, including its renderer/window
       attachment. SAMPLES replaces STATUS only while the module is enabled.
       The selected tab reflects the visible panel, not the internal BEAT FX
       state that keeps a custom pad subtree live. */
    if (window_layer == PERFORMANCE_TAB_LAYER &&
        (image_id == 0x1598u || image_id == 0x1599u)) {
        stock_status_glyph = image;
        memcpy(stock_tab_backing, image, sizeof(stock_tab_backing));
        stock_tab_backing_ready = 1u;
        refresh_initial_performance_tabs_if_ready();
        if (!overlay_panel && !beatfx_reselect_pending)
            native_beatfx_selected = image_id == 0x1598u;
        if (tab_assets_ready && (overlay_panel || samples_callbacks_enabled)) {
            uint8_t neutral[0x54];
            memcpy(neutral, image, sizeof(neutral));
            uint32_t tab = performance_status_image(samples_callbacks_enabled,
                                                    overlay_panel,image_id);
            set_u32(neutral, 0x44, tab);
            original_draw_image(render, neutral);
            return;
        }
    }

    if (window_layer == BEATFX_LEFT_LAYER && image_id == 0x14e9u)
        performance_left_glyph = image;
    if (window_layer == XPAD_RIGHT_LAYER && image_id == 0x14eau)
        performance_right_glyph = image;
    if (image_id == 0x15c9u)
        key_tab_glyph = image;
    if (image_id == 0x15cau)
        stems_tab_glyph = image;
    refresh_initial_performance_tabs_if_ready();

    /* Hardware trace: BeatFxSelectItem/Trash use window-layer 0x1701 and the
       right X-PAD subtree uses 0x1801. Deck summaries below use 0x0301, so
       the full layer is the safe discriminator that image IDs alone lacked. */
    if (overlay_panel && image_id == 0x159au) {
        performance_window = window;
        if (!performance_window_ready) {
            performance_window_ready = 1u;
            log_number("native performance window = ", window);
        }
    }
    /* The pane backdrop opens each pass over the row, so painting the controls
       from it -- and only from it -- gives exactly one row per pass instead of
       one per intercepted call. Everything else inside the subtree is the stock
       pad furniture a live panel stands in for, and is dropped. */
    if (overlay_panel && is_performance_pad_subtree(window_layer)) {
        if (image_id == 0x14e9u || image_id == 0x14eau) {
            original_draw_image(render, image);
            /* The row used to wait here for a stock pad label to clone a face
               from. That label is never drawn -- the pad subtree is images --
               so the condition is what it actually needs: artwork for the
               lettering, or a text model to cut the fills from. */
            if (pad_atlas_ready || pad_text_template_ready || text_template_ready)
                draw_custom_pad_half(render, image, window,
                                     deck_for_pad_subtree(window_layer));
        }
        return;
    }

    if (image_id != 0x15c9u && image_id != 0x15cau) {
        if (rx3_browse_hide_image(image)) return;
        original_draw_image(render, image);
        rx3_browse_caption(render,image,original_draw_text);
        return;
    }
    if (!text_template_ready) {
        original_draw_image(render, image);
        return;
    }

    draw_custom_tabs(render, image);
}


static void hooked_draw_text(void *render, void *text)
{
    draw_calls++;
    if (render_probe_enabled)
        probe_record_text(text);
    if (!RX3_DIAGNOSTIC_ONLY) {
        const uint8_t *glyph = text;
        uint16_t layer;
        struct rx3_text_observation observation;
        memcpy(&layer, glyph + 0x10u, sizeof(layer));
        observation.layer = layer;
        memcpy(observation.box, glyph + 0x18u, sizeof(observation.box));
        memcpy(&observation.text, glyph + 0x34u, sizeof(observation.text));
        observation.length = glyph[0x38u];
        rx3_modules_text_observed(&observation);
        run_pending_ui();
    }
    uint16_t window_layer;
    memcpy(&window_layer, (const uint8_t *)text + 0x10u, sizeof(window_layer));
    if (!RX3_DIAGNOSTIC_ONLY)
        capture_pad_text_template(text, window_layer);
    /* The row is painted from the pane backdrop, so a stock label inside the
       subtree is simply dropped once it has been cloned. */
    if (!RX3_DIAGNOSTIC_ONLY && overlay_panel &&
        is_performance_pad_subtree(window_layer))
        return;
    if (!RX3_DIAGNOSTIC_ONLY && rx3_browse_draw(render,text,original_draw_text,original_draw_image))return;
    original_draw_text(render, text);
    if (RX3_DIAGNOSTIC_ONLY)
        return;
    if (window_layer != HEADER_LAYER)
        return;
    overlay_seen_us = 0;
    if (!text_template_ready) {
        memcpy(text_template, text, sizeof(text_template));
        text_template_ready = 1u;
    }
    refresh_initial_performance_tabs_if_ready();
    main_window_draws++;
    overlay_drawn_us = monotonic_enough_us();
}

static int performance_overlay_is_visible(void)
{
    return overlay_seen_us != 0;
}

static int point_in_rect(int x, int y, int x1, int y1, int x2, int y2)
{
    return x >= x1 && x <= x2 && y >= y1 && y <= y2;
}

static void set_touch_geometry(void *area, int x, int y,
                               unsigned int width, unsigned int height)
{
    if (!area)
        return;
    *(int *)((uint8_t *)area + 8u) = x;
    *(int *)((uint8_t *)area + 0xcu) = y;
    *(unsigned int *)((uint8_t *)area + 0x10u) = width;
    *(unsigned int *)((uint8_t *)area + 0x14u) = height;
}

/* The six Beat FX touch objects used to be repurposed as two decks' worth of
   controls, which is what capped a row at three controls per deck: there are
   only six of them. The row hit-tests its own rectangles now, so while a custom
   panel is up these are parked off screen instead, and handed back untouched on
   the way out. Parking is what keeps a native action from firing in the gaps
   between controls, which is the one place the row declines a touch. */
static void park_native_performance_touches(int parked)
{
    if (!beatfx_touch_areas[0])
        return;
    if (parked) {
        for (unsigned int i = 0; i < 6u; i++)
            set_touch_geometry(beatfx_touch_areas[i], -4096, -4096, 1u, 1u);
    } else {
        for (unsigned int i = 0; i < 6u; i++)
            set_touch_geometry(beatfx_touch_areas[i],
                               stock_touch_geometry[i].x,
                               stock_touch_geometry[i].y,
                               stock_touch_geometry[i].width,
                               stock_touch_geometry[i].height);
    }
}

static void refresh_performance_ui(void)
{
    void *manager = ((void *(*)(void))GET_HMI_MANAGER)();
    void *glyphs[5] = {
        performance_left_glyph, performance_right_glyph,
        key_tab_glyph, stems_tab_glyph, stock_status_glyph
    };
    for (unsigned int i = 0; i < 5u; i++)
        if (glyphs[i])
            ((void (*)(void *, int, void *))REFRESH_GLYPH)(
                manager, -1, glyphs[i]);
}

/* Active touchscreen tabs and physical pad-mode presses return to the
   native display without resetting samples or stem gains. */
static void restore_status(void)
{
    beatfx_reselect_pending = 0u;
    (void)__sync_add_and_fetch(&beatfx_reselect_generation, 1u);
    samples_leave_mode();
    overlay_panel = 0u;
    native_beatfx_selected = 0u;
    pad_row_clear_press();
    park_native_performance_touches(0);
    if (original_set_beatfx_selected)
        original_set_beatfx_selected(0);
    refresh_performance_ui();
}

/* Close before native dispatch, so the chosen pad function paints normally.
   The 1.19 dispatcher can call a dedicated hook too; do not refresh twice. */
static void leave_performance_panel(void)
{
    if (overlay_panel || native_beatfx_selected || beatfx_reselect_pending)
        restore_status();
    else
        samples_leave_mode();
}

static int pad_mode_key_pressed(const void *key_input)
{
    return (*(const uint8_t *)((const uint8_t *)key_input + 0x0bu) & 0x0fu) == 0u;
}

static int hooked_on_key_hot_cue(void *player, const void *input)
{
    if (pad_mode_key_pressed(input))
        leave_performance_panel();
    return original_on_key_hot_cue(player, input);
}

static int hooked_on_key_beat_loop(void *player, const void *input)
{
    if (pad_mode_key_pressed(input))
        leave_performance_panel();
    return original_on_key_beat_loop(player, input);
}

static int hooked_on_key_slip_loop(void *player, const void *input)
{
    if (pad_mode_key_pressed(input))
        leave_performance_panel();
    return original_on_key_slip_loop(player, input);
}

static int hooked_on_key_beat_jump(void *player, const void *input)
{
    if (pad_mode_key_pressed(input))
        leave_performance_panel();
    return original_on_key_beat_jump(player, input);
}

/* 1.19 inlines SLIP LOOP in onPhysicalKey. Never consume a native mode
   event or add a sampler page to its cycle. */
static int hooked_on_physical_key(void *player, const void *input)
{
    const uint8_t *event = input;
    unsigned int code = event[8] | ((unsigned int)event[9] << 8u);
    if (code >= 0x4113u && code <= 0x4116u && pad_mode_key_pressed(input))
        leave_performance_panel();
    return original_on_physical_key(player, input);
}

static void *hooked_beatfx_xpad_ctor(void *object, void *notification)
{
    void *result = original_beatfx_xpad_ctor(object, notification);
    if (!tab_assets_ready)
        install_tab_assets("image table route: Beat FX constructor");
    for (unsigned int i = 0; i < 6u; i++) {
        void *area = *(void **)((uint8_t *)object + 4u + i * 4u);
        beatfx_touch_areas[i] = area;
        if (!area)
            continue;
        stock_touch_geometry[i].x = *(int *)((uint8_t *)area + 8u);
        stock_touch_geometry[i].y = *(int *)((uint8_t *)area + 0xcu);
        stock_touch_geometry[i].width =
            *(unsigned int *)((uint8_t *)area + 0x10u);
        stock_touch_geometry[i].height =
            *(unsigned int *)((uint8_t *)area + 0x14u);
    }
    park_native_performance_touches(overlay_panel != 0u);
    log_line("native BeatFxAndXPad touch areas captured");
    return result;
}

static void select_custom_panel(unsigned int panel)
{
    if (render_probe_enabled)
        log_number("probe: custom panel selected = ", (unsigned long)panel);
    beatfx_reselect_pending = 0u;
    (void)__sync_add_and_fetch(&beatfx_reselect_generation, 1u);
    if (panel != 3u)
        samples_leave_mode();
    overlay_panel = panel;
    /* BeatFxAndXPad is dispatched only while the firmware's binary state is
       BEAT FX. Keep that state active for the lifetime of the custom panel;
       Touchscreen tabs leave it through the explicit STATUS/BEAT FX route. */
    if (original_set_beatfx_selected)
        original_set_beatfx_selected(1);
    park_native_performance_touches(1);
    refresh_performance_ui();
}

static void *finish_beatfx_reselect(void *argument)
{
    unsigned int generation = (unsigned int)(unsigned long)argument;
    /* Ui_CycleTask publishes the requested state every 15 ms. Keep STATUS
       requested for four cycles so the subsequent BEAT FX request is a real
       native display transition even under scheduler jitter. */
    usleep(60000u);
    if (beatfx_reselect_pending &&
        beatfx_reselect_generation == generation && !overlay_panel &&
        original_set_beatfx_selected) {
        log_line("native Beat FX rebuild applied");
        original_set_beatfx_selected(1);
        /* The native state-7 rebuild paints Aqua/Default/Yellow over the tab
           strip. Let that rebuild finish, then restore the persistent custom
           row on top using the already captured native glyphs. */
        usleep(30000u);
        if (beatfx_reselect_pending &&
            beatfx_reselect_generation == generation && !overlay_panel)
            refresh_performance_ui();
    }
    if (beatfx_reselect_generation == generation)
        beatfx_reselect_pending = 0u;
    return 0;
}

static void hooked_set_beatfx_selected(int selected)
{
    unsigned int leaving_custom_panel = overlay_panel != 0u;
    samples_leave_mode();
    if (render_probe_enabled) {
        log_number("probe: beatfx setter selected = ", (unsigned long)selected);
        log_number("probe: beatfx setter leaving_custom = ",
                   (unsigned long)leaving_custom_panel);
    }
    overlay_panel = 0;
    pad_row_clear_press();
    park_native_performance_touches(0);
    /* Ui_CycleTask can echo the provisional STATUS value through this setter.
       While the two-cycle transition is pending, neither that internal 0 nor
       duplicate 1 stores may alter the generation. A new KEY/STEMS selection
       cancels explicitly in select_custom_panel(). */
    if (beatfx_reselect_pending) {
        log_number("native Beat FX rebuild ignored setter = ",
                   (unsigned long)selected);
        return;
    }
    native_beatfx_selected = selected != 0;
    unsigned int generation = __sync_add_and_fetch(
        &beatfx_reselect_generation, 1u);
    if (leaving_custom_panel && selected) {
        pthread_t thread;
        beatfx_reselect_pending = 1u;
        log_line("native Beat FX rebuild scheduled");
        original_set_beatfx_selected(0);
        if (!pthread_create(&thread, 0, finish_beatfx_reselect,
                            (void *)(unsigned long)generation))
            pthread_detach(thread);
        else {
            beatfx_reselect_pending = 0u;
            original_set_beatfx_selected(1);
        }
    } else {
        beatfx_reselect_pending = 0u;
        original_set_beatfx_selected(selected);
    }
    refresh_performance_ui();
}


/* Handle only a new touchscreen press; release/drag ownership stays in
   hooked_solve_touch so a held finger cannot toggle a tab twice. */
static int performance_tab_touch(int x, int y)
{
    const struct rx3_pad_row *left = row_for_slot(0u);
    const struct rx3_pad_row *right = row_for_slot(1u);
    if ((overlay_panel == 1u && !left) ||
        (overlay_panel == 2u && !right) ||
        (overlay_panel == 3u && !samples_callbacks_enabled))
        restore_status();
    if ((!!left != !!right) && point_in_rect(x, y, 1090, 363 + CUSTOM_TAB_OFFSET_Y,
                                            1270, CUSTOM_TAB_TOUCH_BOTTOM)) {
        const struct rx3_pad_row *single = left ? left : right;
        if (overlay_panel == single->panel_id) restore_status();
        else select_custom_panel(single->panel_id);
        log_line("touch action = single feature panel");
        return 1;
    }
    if (point_in_rect(x, y, 1090, 363 + CUSTOM_TAB_OFFSET_Y,
                      1179, CUSTOM_TAB_TOUCH_BOTTOM)) {
        if (!left) return 0;
        if (overlay_panel == left->panel_id) restore_status();
        else select_custom_panel(left->panel_id);
        log_line("touch action = left feature panel");
        return 1;
    } else if (point_in_rect(x, y, 1181, 363 + CUSTOM_TAB_OFFSET_Y,
                             1270, CUSTOM_TAB_TOUCH_BOTTOM)) {
        if (!right) return 0;
        if (overlay_panel == right->panel_id) restore_status();
        else select_custom_panel(right->panel_id);
        log_line("touch action = right feature panel");
        return 1;
    } else if (samples_callbacks_enabled && tab_assets_ready &&
               point_in_rect(x, y, 1090, 432, 1179, 482)) {
        if (overlay_panel == 3u) restore_status();
        else samples_enter_mode();
        return 1;
    } else if (!samples_callbacks_enabled &&
               point_in_rect(x, y, 1090, 432, 1179, 482)) {
        restore_status();
        return 1;
    } else if (point_in_rect(x, y, 1181, 432, 1270, 482)) {
        if (!overlay_panel && (native_beatfx_selected || beatfx_reselect_pending))
            restore_status();
        else hooked_set_beatfx_selected(1);
        return 1;
    }
    return 0;
}

static void hooked_solve_touch(void *handler, const void *status,
                               const void *mode)
{
    touch_calls++;
    if (RX3_DIAGNOSTIC_ONLY) {
        original_solve_touch(handler, status, mode);
        return;
    }
    const uint8_t *event = status;
    int pressed = event[0] != 0;
    int x = *(const int *)(event + 4u);
    int y = *(const int *)(event + 8u);
    if (x > 1280 || y > 720) {
        x = x * 1280 / 4096;
        y = y * 720 / 4096;
    }

    if (rx3_browse_touch(pressed ? x : *(const int *)((const uint8_t *)handler+8u),
                         pressed ? y : *(const int *)((const uint8_t *)handler+0xcu),pressed)) {
        *(uint8_t *)((uint8_t *)handler+4u)=(uint8_t)pressed;
        *(int *)((uint8_t *)handler+8u)=x;
        *(int *)((uint8_t *)handler+0xcu)=y;
        return;
    }

    if (captured_touch) {
        /* The capture is what makes sliding off a control mean something: every
           event of the gesture arrives here, including the release, wherever on
           the screen the finger finally leaves. */
        if (captured_touch == 4u)
            pad_row_touch(row_for_id(overlay_panel), captured_touch_deck,
                          x - (int)captured_touch_deck * RX3_PAD_DECK_STRIDE,
                          pressed ? 2u : 0u);
        *(uint8_t *)((uint8_t *)handler + 4u) = (uint8_t)pressed;
        *(int *)((uint8_t *)handler + 8u) = x;
        *(int *)((uint8_t *)handler + 0xcu) = y;
        if (!pressed)
            captured_touch = 0;
        return;
    }

    if (pressed && !*(const uint8_t *)((const uint8_t *)handler + 4u) &&
        performance_overlay_is_visible()) {
        if (performance_tab_touch(x, y)) captured_touch = 3u;
        if (captured_touch) {
            *(uint8_t *)((uint8_t *)handler + 4u) = 1;
            *(int *)((uint8_t *)handler + 8u) = x;
            *(int *)((uint8_t *)handler + 0xcu) = y;
            return;
        }
    }
    if (pressed && !*(const uint8_t *)((const uint8_t *)handler + 4u) &&
        performance_overlay_is_visible() &&
        y >= RX3_PAD_TOUCH_TOP && y <= RX3_PAD_TOUCH_BOTTOM) {
        unsigned int deck = x >= RX3_PAD_DECK_STRIDE ? 1u : 0u;
        /* A press in a gap between controls is declined, and falls through to
           the player with the native areas parked out of its way. */
        if (pad_row_touch(row_for_id(overlay_panel), deck,
                          x - (int)deck * RX3_PAD_DECK_STRIDE, 1u)) {
            captured_touch_deck = deck;
            captured_touch = 4u;
            *(uint8_t *)((uint8_t *)handler + 4u) = 1u;
            *(int *)((uint8_t *)handler + 8u) = x;
            *(int *)((uint8_t *)handler + 0xcu) = y;
            return;
        }
    }
    original_solve_touch(handler, status, mode);
}

/* Audio mixing. */

/* Stable core service used by audio features. A feature receives only a deck
   index; its mutable per-deck state remains private to that feature. */
static int deck_index_for_reader(const void *reader)
{
    for (unsigned int deck = 0; deck < 2u; deck++)
        if (deck_readers[deck] == reader)
            return (int)deck;
    return -1;
}

static struct stems_deck_context *context_for_player(const void *player)
{
    unsigned int player_no = *(const uint8_t *)((const uint8_t *)player + 0x26u);
    if (player_no < 1u || player_no > 2u)
        return 0;
    return &stems_decks[player_no - 1u];
}

static int block_is_silent(const Float2 *output, unsigned long frames)
{
    for (unsigned long i = 0; i < frames; i++)
        if (output[i].left != 0.0f || output[i].right != 0.0f)
            return 0;
    return 1;
}

/* rbp publishes the audio device format here. Features that size buffers from
   it cannot be built before this point. */
static void hooked_audio_start(void *engine, void *device)
{
    unsigned int rate = 44100u;
    audio_start_calls++;
    if (device) {
        void **vtable = *(void ***)device;
        double sample_rate = ((audio_sample_rate_fn)vtable[0x44u / 4u])(device);
        if (sample_rate > 0.0 && sample_rate <= 192000.0)
            rate = (unsigned int)sample_rate;
    }
    original_audio_start(engine, device);
    if (RX3_DIAGNOSTIC_ONLY) {
        log_line("diagnostic: audioDeviceAboutToStart observed");
        return;
    }
    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++)
        if (runtime_features[i].active && runtime_features[i].audio_started)
            runtime_features[i].audio_started(rate);
    rx3_modules_audio_started(rate);
}


/* Shared hook replacement. Feature-specific hooks are composed below. */
#include "../stems/rx3_stems_feature.h"
#include "../logo/rx3_logo_feature.h"
#include "../theme-white/rx3_theme_feature.h"
#include "../samples/rx3_samples_feature.h"

static int hooked_load(void *reader, const void *track_info)
{
    unsigned int channel = *(const uint32_t *)((const uint8_t *)reader + 0x20u);
    if (channel >= 2u) {
        int result = original_load(reader, track_info);
        log_number("feature dispatch ignored: unknown PcmReader channel = ",
                   channel);
        return result;
    }

    deck_readers[channel] = 0;
    __sync_synchronize();
    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++)
        if (runtime_features[i].active &&
            runtime_features[i].track_will_load)
            runtime_features[i].track_will_load(channel, reader, track_info);

    rx3_modules_track_will_load(channel, reader, track_info);
    int result = original_load(reader, track_info);
    __sync_synchronize();
    deck_readers[channel] = reader;
    __sync_synchronize();

    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++)
        if (runtime_features[i].active && runtime_features[i].track_did_load)
            runtime_features[i].track_did_load(channel, reader, track_info);
    rx3_modules_track_did_load(channel, reader, track_info);
    return result;
}

static unsigned int configure_features(void)
{
    unsigned int active = 0;
    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++) {
        runtime_features[i].active = runtime_features[i].configured &&
                                     runtime_features[i].configured();
        if (runtime_features[i].active) {
            log_line("module configured:");
            log_line(runtime_features[i].name);
            active++;
        }
    }
    return active;
}

static unsigned int install_features(void)
{
    unsigned int active = 0;
    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++) {
        struct rx3_runtime_feature *feature = &runtime_features[i];
        if (!feature->active)
            continue;
        if ((!feature->install || feature->install()) &&
            (!feature->row || rx3_panels.register_row(feature->row))) {
            log_line("module active:");
            log_line(feature->name);
            active++;
            continue;
        }
        log_line("optional feature disabled: hook guard rejected");
        log_line(feature->name);
        if (feature->row) rx3_panels.unregister_row(feature->row);
        if (feature->remove)
            feature->remove();
        feature->active = 0;
    }
    return active;
}

static void remove_features(void)
{
    for (unsigned int i = RUNTIME_FEATURE_COUNT; i > 0u; i--) {
        struct rx3_runtime_feature *feature = &runtime_features[i - 1u];
        if (feature->row) rx3_panels.unregister_row(feature->row);
        if (feature->remove)
            feature->remove();
        feature->active = 0;
    }
}

/* Lifecycle. */

/* Both teardown paths take the same hooks out in the same order: the error exit
   of the installer, and the destructor. They were two copies, so adding a hook
   and updating only one of them left that hook installed on the path nobody
   exercises until something has already gone wrong. */
static void uninstall_performance_hooks(void)
{
    park_native_performance_touches(0);
    remove_features();
    logo_feature_remove();
    uninstall_hook(&hw_fill_rect_hook);
    uninstall_hook(&beatfx_xpad_ctor_hook);
    uninstall_hook(&physical_pad_mode_hook);
    uninstall_hook(&beat_jump_hook);
    uninstall_hook(&slip_loop_hook);
    uninstall_hook(&beat_loop_hook);
    uninstall_hook(&hot_cue_hook);
    uninstall_hook(&set_beatfx_hook);
    uninstall_hook(&touch_hook);
    uninstall_hook(&draw_image_hook);
    uninstall_hook(&image_info_hook);
    uninstall_hook(&draw_text_hook);
    uninstall_hook(&load_hook);
    uninstall_hook(&audio_start_hook);
    original_audio_start = 0;
}

/* LD_PRELOAD is inherited by exec'ed utilities. They must never touch player
   addresses, truncate its readiness marker, or run its teardown. */
static int player_process_initialized;
static int is_player_process(void)
{
    char name[16];
    int fd = open("/proc/self/comm", O_RDONLY);
    if (fd < 0) return 0;
    int length = read(fd, name, sizeof(name));
    close(fd);
    return length == 4 && !memcmp(name, "rbp\n", 4u);
}

__attribute__((constructor)) static void initialize(void)
{
    if (!is_player_process()) return;
    player_process_initialized = 1;
    rx3_log_configure();
    /* An earlier marker must not survive a rejected startup. */
    int ready_fd = open(READY_FILE, O_WRONLY | O_TRUNC, 0600);
    if (ready_fd >= 0) close(ready_fd);
    /* Each feature is a module of its own and announces itself through the
       environment its module.sh exports. The core installs either way, so that
       key shift works without stems and stems works without key shift. */
    stems_dir = getenv("RX3_STEMS_DIR");
    if (stems_dir && !stems_dir[0])
        stems_dir = 0;
    const char *samples = getenv("RX3_SAMPLES_DIR");
    samples_enabled = samples && samples[0] != '\0';
    /* The first character selects the display mode, as the reference reads it:
       l starts light, d runs the global dark remap, s starts dark and leaves
       the switch in Utility. Anything else non-empty is the switchable mode,
       which is what the module exports. */
    /* On unless the operator says otherwise. The sentinel file is the other
       half of the switch, for a deck that is already misbehaving. */
    const char *messages = getenv("RX3_MESSAGES");
    messages_enabled = !(messages && messages[0] == '0');
    (void)rx3_message_allowed();

    const char *theme = getenv("RX3_THEME");
    theme_enabled = theme && theme[0] != '\0';
    if (theme_enabled) {
        /* One letter chooses the starting mode, because the environment is the
           only channel a module has into the core. The four are distinct
           states rather than one switch: what the deck shows at the first
           frame, and whether it moves afterwards, are separate questions. */
        theme_light = theme[0] == 'l';
        theme_light_active = theme_light;
        theme_global_dark = theme[0] == 'd';
        theme_light_armed = theme[0] == 'w';
        if (theme_global_dark) {
            log_line("global dark theme active (sentinel: " THEME_DARK_SENTINEL ")");
        } else if (theme_light_armed) {
            theme_start_light_not_before_us = monotonic_enough_us() + 1000000u;
            log_line("display mode: light, held back until the player has painted once");
        } else if (theme_light) {
            log_line("display mode: light from the first frame");
        } else {
            log_line("display mode: dark to begin with, switch it in Utility");
        }
    }
    const char *logo = getenv("RX3_LOGO");
    logo_enabled = logo && logo[0] == '1';
    const char *delay = getenv("RX3_TAB_DELAY_MS");
    if (delay) {
        unsigned long ms = 0;
        for (const char *c = delay; *c >= '0' && *c <= '9'; c++)
            ms = ms * 10u + (unsigned long)(*c - '0');
        if (ms) {
            tab_install_not_before_us = monotonic_enough_us() + (uint64_t)ms * 1000u;
            log_number("diagnostic: image table install held back, ms = ", ms);
        }
    }
    const char *probe = getenv("RX3_RENDER_PROBE");
    render_probe_enabled = probe && probe[0] == '1';
    if (render_probe_enabled)
        log_line("render probe active: " RENDER_PROBE_FILE);
    /* Read once, here rather than from a feature slot: the artwork is not a
       tab, it has no controls, and the player asks for it while it builds the
       screen rather than when a deck loads. */
    if (logo_enabled && !logo_feature_install()) {
        log_line("module failed: logo artwork or placement");
        logo_feature_remove();
        return;
    }
    unsigned int configured = configure_features();
    if (!configured && !main_logo_ready) {
        unsigned int standalone = rx3_modules_start();
        if (rx3_modules_failures()) { rx3_modules_stop(); return; }
        if (!rx3_panel_count() && !rx3_image_count() && !rx3_browse_count()) {
            if (standalone) {
                publish_ready();
                log_line("RX3 performance hook active");
            }
            return;
        }
    }

    for (unsigned int i = 0; i < 2u; i++) {
        stems_decks[i].selection = 0u;
        stems_decks[i].transition_cursor = TRANSITION_FRAMES;
    }

    /* PcmReader::load is the core deck-identity service used independently by
       both features. The remaining audio/pad hooks belong to stems alone. */
    original_load = (load_fn)install_hook(
        &load_hook, PCM_LOAD, load_guard, (void *)hooked_load);
    if (!original_load) {
        log_line("rejected: unexpected PcmReader::load prologue");
        goto reject_performance_hooks;
    }

    original_set_beatfx_selected = (set_beatfx_selected_fn)install_hook(
        &set_beatfx_hook, SET_BEATFX_STORAGE, set_beatfx_guard,
        (void *)hooked_set_beatfx_selected);
    if (!original_set_beatfx_selected) {
        log_line("rejected: unexpected Beat FX state setter prologue");
        goto reject_performance_hooks;
    }

    original_on_key_hot_cue = (on_key_pad_fn)install_hook(
        &hot_cue_hook, ON_KEY_HOT_CUE, hot_cue_guard,
        (void *)hooked_on_key_hot_cue);
    original_on_key_beat_loop = (on_key_pad_fn)install_hook(
        &beat_loop_hook, ON_KEY_BEAT_LOOP, pad_mode_guard,
        (void *)hooked_on_key_beat_loop);
    original_on_key_slip_loop = (on_key_pad_fn)install_hook(
        &slip_loop_hook, ON_KEY_SLIP_LOOP, pad_mode_guard,
        (void *)hooked_on_key_slip_loop);
    original_on_key_beat_jump = (on_key_pad_fn)install_hook(
        &beat_jump_hook, ON_KEY_BEAT_JUMP, pad_mode_guard,
        (void *)hooked_on_key_beat_jump);
    if (!original_on_key_hot_cue || !original_on_key_beat_loop ||
        !original_on_key_slip_loop || !original_on_key_beat_jump) {
        log_line("rejected: unexpected hardware pad-mode key prologue");
        goto reject_performance_hooks;
    }

    if (samples_enabled) {
        static const uint8_t physical_guard[8] = {0xb8,0x30,0xd1,0xe1,0x00,0xc0,0xa0,0xe3};
        original_on_physical_key = (on_key_pad_fn)install_hook(
            &physical_pad_mode_hook, 0x00306b78u, physical_guard,
            (void *)hooked_on_physical_key);
        if (!original_on_physical_key) {
            samples_enabled = 0;
            log_line("samples disabled: physical pad-mode dispatcher guard rejected");
        }
    }

    original_beatfx_xpad_ctor = (beatfx_xpad_ctor_fn)install_hook(
        &beatfx_xpad_ctor_hook, BEATFX_XPAD_CTOR, beatfx_xpad_ctor_guard,
        (void *)hooked_beatfx_xpad_ctor);
    if (!original_beatfx_xpad_ctor) {
        log_line("rejected: unexpected BeatFxAndXPad constructor prologue");
        goto reject_performance_hooks;
    }


    /* The launch patch extends the lookup bound to include the private IDs.
       Both instructions are independent of PC and can be relocated intact. */
    /* movw r3, #EXTENDED_IMAGE_COUNT - 1, which is what module.sh writes.
       This word, the count above and the module's replacement string are one
       fact in three files; a test compares them rather than trusting them. */
    static const uint8_t image_info_guard[8] = {
        0xa5, 0x36, 0x01, 0xe3, 0x03, 0x00, 0x50, 0xe1
    };
    original_image_info = (image_info_fn)install_hook(
        &image_info_hook, 0x001d192c, image_info_guard, (void *)hooked_image_info);
    if (!original_image_info) {
        static const uint8_t stock_image_info_guard[8] = {
            0xcc, 0x35, 0x01, 0xe3, 0x03, 0x00, 0x50, 0xe1
        };
        original_image_info = (image_info_fn)install_hook(
            &image_info_hook, 0x001d192c, stock_image_info_guard, (void *)hooked_image_info);
    }
    if (!original_image_info)
        log_line("warning: early image lookup hook unavailable");

    original_draw_text = (draw_text_fn)install_hook(
        &draw_text_hook, PAL_DRAW_TEXT, draw_text_guard, (void *)hooked_draw_text);
    if (!original_draw_text) {
        log_line("rejected: unexpected NS_PALRender_DrawText prologue");
        goto reject_performance_hooks;
    }

    original_draw_image = (draw_image_fn)install_hook(
        &draw_image_hook, PAL_DRAW_IMAGE, draw_image_guard, (void *)hooked_draw_image);
    if (!original_draw_image) {
        log_line("rejected: unexpected NS_PALRender_DrawImage prologue");
        goto reject_performance_hooks;
    }

    original_solve_touch = (solve_touch_fn)install_hook(
        &touch_hook, SOLVE_TOUCH, touch_guard, (void *)hooked_solve_touch);
    if (!original_solve_touch) {
        log_line("rejected: unexpected solveCoordToKey prologue");
        goto reject_performance_hooks;
    }

    if (install_features() != configured)
        goto reject_performance_hooks;

    /* Consumers start only after the legacy providers have succeeded. */
    (void)rx3_modules_start();
    if (rx3_modules_failures())
        goto reject_performance_hooks;
    if (rx3_modules_uses_audio()) {
        original_audio_start = (audio_start_fn)install_hook(
            &audio_start_hook, AUDIO_START, audio_start_guard, (void *)hooked_audio_start);
        if (!original_audio_start) goto reject_performance_hooks;
    }


    state_thread_running = 1;
    if (!pthread_create(&state_thread, 0, watch_patch_state, 0))
        state_thread_started = 1;
    else
        log_line("warning: patch-state watcher could not start");
    publish_ready();
    log_line("RX3 performance hook active");
    return;

reject_performance_hooks:
    log_line("runtime failed: selected modules not ready");
    rx3_modules_stop();
    uninstall_performance_hooks();
    original_beatfx_xpad_ctor = 0;
    original_on_key_beat_jump = 0;
    original_on_key_slip_loop = 0;
    original_on_key_beat_loop = 0;
    original_on_key_hot_cue = 0;
    original_set_beatfx_selected = 0;
    original_solve_touch = 0;
    original_draw_image = 0;
    original_draw_text = 0;
    original_load = 0;
}

__attribute__((destructor)) static void finalize(void)
{
    if (!player_process_initialized) return;
    __atomic_store_n(&state_thread_running, 0, __ATOMIC_SEQ_CST);
    if (state_thread_started) {
        pthread_join(state_thread, 0);
        state_thread_started = 0;
    }
    rx3_modules_stop();
    uninstall_performance_hooks();
    for (unsigned int i = 0; i < 2u; i++) {
        for (unsigned int feature = 0;
             feature < RUNTIME_FEATURE_COUNT; feature++)
            if (runtime_features[feature].destroy_deck)
                runtime_features[feature].destroy_deck(i);
    }
}
