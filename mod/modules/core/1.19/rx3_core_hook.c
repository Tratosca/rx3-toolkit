// SPDX-License-Identifier: MPL-2.0
/*
 * Modular two-deck performance core for XDJ-RX3 firmware 1.19.
 *
 * The core is the sole broker for guarded inline hooks, deck identity, native
 * rendering and touch routing. Optional Stems and Key Shift features own
 * disjoint state and hook groups and can fail independently.
 *
 * Both pads blink while a sidecar is being read and hold their colour once it
 * is resident, so the operator can see when the toggles become effective.
 *
 * Stems are copied into anonymous RAM before publication to the audio
 * thread. Removing the USB drive after a completed load therefore leaves no
 * active file mapping. int16 and float32 payloads are supported.
 *
 * PcmReader operates at 44,100 frames per second. ReaderImpl converts source
 * files before this buffer, so the sidecar frame index remains in the same
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
#define TOUCH_BUTTON_ON  ((unsigned long)0x00360594)
#define TOUCH_BUTTON_HOLD ((unsigned long)0x00360610)
#define TOUCH_TOGGLE_ON  ((unsigned long)0x003606dc)
#define TOUCH_TOGGLE_OFF ((unsigned long)0x00360728)
#define TOUCH_XPAD_ON    ((unsigned long)0x00360a00)
#define TOUCH_XPAD_OFF   ((unsigned long)0x00360a44)
#define TOUCH_XPAD_HOLD  ((unsigned long)0x00360e5c)
#define TOUCH_BUTTON_OFF ((unsigned long)0x00363280)
#define AUDIO_START    ((unsigned long)0x000447b8)
/* dsp::TimeStretch::getStreamAt is the deck's playback stream. It wraps
   PcmReader::getStreamAt and is the speed and master-tempo stage, so its output
   is what the deck actually plays. PcmReader::getStreamAt itself is shared with
   Player::update's BPM and waveform analysis scan, which walks the whole track
   out of order; a sequential DSP cannot sit there. TimeStretch+4 is the reader,
   which identifies the deck. */
#define GET_HMI_MANAGER ((unsigned long)0x001d09b4)
#define REFRESH_GLYPH   ((unsigned long)0x001d07b0)
#define SET_BEATFX_STORAGE ((unsigned long)0x001331fc)
#if defined(RX3_EMULATOR_BUILD)
#include "rx3_core_emulator_keys.h"
#endif

#define LOG_FILE  "/tmp/rx3-stems.log"
#define READY_FILE "/tmp/rx3-performance.ready"

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
#define TAB_IMAGE_COUNT 4u
#define STOCK_IMAGE_COUNT 0x15cdu
#define EXTENDED_IMAGE_COUNT 0x1604u
#define IMAGE_TABLE_POINTER ((unsigned long)0x05a14f60)
#define TAB_KEY_PATH "/root/pdj/rx3-key-selected.rgb565"
#define TAB_STEMS_PATH "/root/pdj/rx3-stems-selected.rgb565"
#define TAB_STATUS_NONE_PATH "/root/pdj/rx3-status-none-selected.rgb565"
#define TAB_KEY_NONE_PATH "/root/pdj/rx3-none-selected.rgb565"

/* Reject a stem above this fraction of estimated available RAM. */
#define MEM_NUMERATOR   3
#define MEM_DENOMINATOR 5

/* Types and libc declarations. */

typedef unsigned int   size_t;
typedef int            ssize_t;
typedef long           off_t;
typedef unsigned char  uint8_t;
typedef unsigned short uint16_t;
typedef short          int16_t;
typedef unsigned int   uint32_t;
typedef unsigned long long uint64_t;
typedef unsigned long pthread_t;

extern int      open(const char *, int, ...);
extern ssize_t  read(int, void *, size_t);
extern ssize_t  write(int, const void *, size_t);
extern int      close(int);
extern off_t    lseek(int, off_t, int);
extern void    *mmap(void *, size_t, int, int, int, off_t);
extern int      munmap(void *, size_t);
extern int      mprotect(void *, size_t, int);
extern long     sysconf(int);
extern void    *memcpy(void *, const void *, size_t);
extern void    *memset(void *, int, size_t);
extern int      memcmp(const void *, const void *, size_t);
extern char    *getenv(const char *);
extern int      pthread_create(pthread_t *, const void *, void *(*)(void *), void *);
extern int      pthread_detach(pthread_t);
extern int      usleep(unsigned int);
extern int      gettimeofday(void *, void *);

#define O_RDONLY 0
#define O_WRONLY 1
#define O_NONBLOCK 04000
#define O_CREAT  0100
#define O_TRUNC  01000
#define O_APPEND 02000
#define SEEK_SET 0
#define SEEK_END 2
#define PROT_READ  1
#define PROT_WRITE 2
#define PROT_EXEC  4
#define MAP_PRIVATE   2
#define MAP_ANONYMOUS 0x20
#define MAP_FAILED ((void *)-1)
#define _SC_PAGESIZE 30

/* Data model. */

typedef struct { float left, right; } Float2;
typedef struct { int16_t left, right; } Short2;

#include "rx3_feature_api.h"
#include "../../keyshift/1.19/rx3_keyshift_decl.h"
#include "../../stems/1.19/rx3_stems_decl.h"

typedef unsigned long (*get_stream_fn)(void *, unsigned long, Float2 *, unsigned long);
typedef int (*load_fn)(void *, const void *);
typedef int (*on_key_pad_fn)(void *, const void *);
typedef void (*check_slip_led_fn)(void *, void *);
typedef void (*set_led_color_fn)(void *, int, int, const void *);
/* uif::Led::setState(State, period_ms, started_at_ms, long, BrightnessState).
   With State 2 the panel runs the blink itself, so the rate of the LED refresh
   this hook rides on does not affect the cadence. */
typedef void (*set_led_state_fn)(void *, int, unsigned int, unsigned int, long, int);
typedef void (*draw_text_fn)(void *, void *);
typedef void (*draw_image_fn)(void *, void *);
typedef void (*solve_touch_fn)(void *, const void *, const void *);
typedef void *(*beatfx_xpad_ctor_fn)(void *, void *);
typedef void (*touch_area_fn)(void *);
typedef void (*touch_area_hold_fn)(void *, unsigned int, unsigned int);
typedef void (*audio_start_fn)(void *, void *);
typedef int (*audio_buffer_size_fn)(void *);
typedef double (*audio_sample_rate_fn)(void *);
typedef void (*set_beatfx_selected_fn)(int);
typedef int (*get_beatfx_selected_fn)(void);

/* Expected prologues, checked before writing executable code. */
static const uint8_t get_stream_guard[8] = {
    0x9c, 0xc0, 0xd0, 0xe5, 0xf0, 0x45, 0x2d, 0xe9
};
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
static const uint8_t beatfx_xpad_ctor_guard[8] = {
    0xf0, 0x4f, 0x2d, 0xe9, 0x7c, 0xd0, 0x4d, 0xe2
};
static const uint8_t touch_button_on_guard[8] = {
    0x20, 0xc0, 0xd0, 0xe5, 0x30, 0x40, 0x2d, 0xe9
};
static const uint8_t touch_button_hold_guard[8] = {
    0xb1, 0x00, 0x52, 0xe3, 0x70, 0x40, 0x2d, 0xe9
};
static const uint8_t touch_toggle_on_guard[8] = {
    0x10, 0x40, 0x2d, 0xe9, 0x00, 0xe0, 0xa0, 0xe1
};
static const uint8_t touch_toggle_off_guard[8] = {
    0x00, 0xc0, 0xa0, 0xe1, 0x04, 0x00, 0x90, 0xe5
};
static const uint8_t touch_button_off_guard[8] = {
    0x20, 0xc0, 0xd0, 0xe5, 0x10, 0x40, 0x2d, 0xe9
};
static const uint8_t touch_xpad_on_guard[8] = {
    0x10, 0x40, 0x2d, 0xe9, 0x10, 0xd0, 0x4d, 0xe2
};
static const uint8_t touch_xpad_off_guard[8] = {
    0x30, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
static const uint8_t touch_xpad_hold_guard[8] = {
    0x08, 0x30, 0x90, 0xe5, 0x30, 0x40, 0x2d, 0xe9
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

static volatile void *deck_readers[2];
static volatile int state_thread_running;
static volatile uint64_t overlay_seen_us;
static volatile uint64_t overlay_drawn_us;
static volatile unsigned int captured_touch;
static volatile unsigned int overlay_panel;
static volatile unsigned long draw_calls;
static volatile unsigned long main_window_draws;
static volatile unsigned long image_draw_calls;
static volatile unsigned long custom_tab_draws;
static volatile unsigned long custom_pad_draws;
static volatile unsigned long touch_calls;
static volatile unsigned int stock_tab_backing_ready;
static uint8_t stock_tab_backing[0x54];
static volatile unsigned int tab_assets_ready;
static volatile unsigned int tab_assets_installing;
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
static volatile void *captured_native_touch;
/* Which control is held, so the row can paint it pressed. -1 is nothing. */
static volatile int pressed_deck = -1;
static volatile int pressed_control = -1;
static void *performance_left_glyph;
static void *performance_right_glyph;
static void *key_tab_glyph;
static void *stems_tab_glyph;
static void *stock_status_glyph;
static volatile unsigned int beatfx_reselect_generation;
static volatile unsigned int beatfx_reselect_pending;
#if defined(RX3_EMULATOR_BUILD)
/* Host-only state. The deployable hook is compiled without this branch. */
static volatile unsigned int emulator_forced_panel;
static volatile unsigned int emulator_panel_applied;
static unsigned int emulator_touch_sequence;
/* UiKey_KeyPush's own first eight bytes. Checked before the first call for the
   same reason install_hook checks a prologue: a firmware whose entry point has
   moved must be refused, not called. */
static const uint8_t ui_key_push_guard[8] = {
    0x30, 0x40, 0x2d, 0xe9, 0x00, 0x50, 0xa0, 0xe1
};
static const uint8_t browse_key_pump_guard[8] = {
    0xf8, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe3
};
static const uint8_t set_flg_guard[8] = {
    0x01, 0x00, 0x40, 0xe2, 0x1f, 0x00, 0x50, 0xe3
};
static const uint8_t gui_invalidate_guard[8] = {
    0x01, 0x0a, 0x10, 0xe3, 0x10, 0x40, 0x2d, 0xe9
};
static const uint8_t player_innards_guard[8] = {
    0x01, 0xc0, 0xa0, 0xe1, 0x03, 0x10, 0xa0, 0xe1
};
/* Indexed by channel - 1, so deck 1 is slot 0. */
static void *volatile player_innards[2];
static volatile int ui_key_push_usable = -1;
#endif

static const struct rx3_panel_feature *panel_for_id(unsigned int panel_id);
static int deck_index_for_reader(const void *reader);
#if defined(RX3_EMULATOR_BUILD)
static void emulator_poll_touch(void);
static void emulator_activate_initial_panel(void);
#endif

static int stems_feature_configured(void);
static int stems_feature_install(void);
static void stems_feature_remove(void);
static void stems_feature_track_will_load(unsigned int deck, void *reader,
                                          const void *track_info);
static void stems_feature_track_did_load(unsigned int deck, void *reader,
                                         const void *track_info);
static void stems_feature_destroy_deck(unsigned int deck);
static int keyshift_feature_configured(void);
static int keyshift_feature_install(void);
static void keyshift_feature_remove(void);
static void keyshift_feature_track_did_load(unsigned int deck, void *reader,
                                            const void *track_info);
static const struct rx3_panel_feature keyshift_panel;
static const struct rx3_panel_feature stems_panel;

#define RUNTIME_FEATURE_COUNT 2u

static struct rx3_runtime_feature runtime_features[RUNTIME_FEATURE_COUNT] = {
    {
        "keyshift", 0, &keyshift_panel,
        keyshift_feature_configured, keyshift_feature_install,
        keyshift_feature_remove, 0, keyshift_feature_track_did_load,
        rx3_keyshift_start_audio, rx3_keyshift_report,
        rx3_keyshift_destroy_deck
    },
    {
        "stems", 0, &stems_panel,
        stems_feature_configured, stems_feature_install,
        stems_feature_remove, stems_feature_track_will_load,
        stems_feature_track_did_load, 0, 0, stems_feature_destroy_deck
    }
};

struct installed_hook {
    unsigned long address;
    uint8_t       original[8];
    void         *trampoline;
};

static struct installed_hook get_stream_hook;
static struct installed_hook load_hook;
static struct installed_hook pad_hook;
static struct installed_hook hot_cue_hook;
static struct installed_hook beat_loop_hook;
static struct installed_hook slip_loop_hook;
static struct installed_hook beat_jump_hook;
static struct installed_hook slip_led_hook;
static struct installed_hook draw_text_hook;
static struct installed_hook draw_image_hook;
static struct installed_hook touch_hook;
static struct installed_hook beatfx_xpad_ctor_hook;
static struct installed_hook touch_button_on_hook;
static struct installed_hook touch_button_hold_hook;
static struct installed_hook touch_button_off_hook;
static struct installed_hook touch_toggle_on_hook;
static struct installed_hook touch_toggle_off_hook;
static struct installed_hook touch_xpad_on_hook;
static struct installed_hook touch_xpad_off_hook;
static struct installed_hook touch_xpad_hold_hook;
static struct installed_hook audio_start_hook;
static struct installed_hook timestretch_operate_hook;
static struct installed_hook timestretch_fgpr_hook;
static struct installed_hook set_beatfx_hook;
static draw_text_fn original_draw_text;
static draw_image_fn original_draw_image;
static solve_touch_fn original_solve_touch;
static beatfx_xpad_ctor_fn original_beatfx_xpad_ctor;
static touch_area_fn original_touch_button_on;
static touch_area_hold_fn original_touch_button_hold;
static touch_area_fn original_touch_button_off;
static touch_area_fn original_touch_toggle_on;
static touch_area_fn original_touch_toggle_off;
static touch_area_fn original_touch_xpad_on;
static touch_area_fn original_touch_xpad_off;
static touch_area_hold_fn original_touch_xpad_hold;
static audio_start_fn original_audio_start;
static timestretch_operate_fn original_timestretch_operate;
static timestretch_operate_fn original_timestretch_fgpr;
static set_beatfx_selected_fn original_set_beatfx_selected;
/* Logging. */

static size_t str_length(const char *s)
{
    size_t n = 0;
    while (s[n])
        n++;
    return n;
}

static void log_line(const char *message)
{
    int fd = open(LOG_FILE, O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd < 0)
        return;
    (void)write(fd, message, str_length(message));
    (void)write(fd, "\n", 1);
    close(fd);
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
    return context->reader && context->armed && !context->vocal.data;
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

static void install_tab_assets(void)
{
    if (tab_assets_ready)
        return;
    if (!__sync_bool_compare_and_swap(&tab_assets_installing, 0u, 1u))
        return;
    static const char *paths[TAB_IMAGE_COUNT] = {
        TAB_KEY_PATH,
        TAB_STEMS_PATH,
        TAB_STATUS_NONE_PATH,
        TAB_KEY_NONE_PATH
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

    uint8_t *stock_table = *(uint8_t **)IMAGE_TABLE_POINTER;
    if (!stock_table) {
        tab_assets_installing = 0u;
        return;
    }
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

    __sync_synchronize();
    *(uint8_t **)IMAGE_TABLE_POINTER = table;
    __sync_synchronize();
    tab_assets_ready = 1u;
    log_line("extended private KEY/STEMS image table installed");
}

static void *watch_patch_state(void *unused)
{
    (void)unused;
    unsigned int ticks = 0;
    int last_phase = -1;
    while (state_thread_running) {
        usleep(50000u);
        if (!tab_assets_ready)
            install_tab_assets();
#if defined(RX3_EMULATOR_BUILD)
        emulator_activate_initial_panel();
#endif
        /* Nothing else invalidates the pad windows while a sidecar is read, so
           the blink has to ask for the redraw that carries its own parity. */
        const struct rx3_panel_feature *panel = panel_for_id(overlay_panel);
        if (panel && panel->needs_refresh && panel->needs_refresh() &&
            performance_window_ready) {
            int phase = blink_phase_is_on();
            if (phase != last_phase) {
                last_phase = phase;
                refresh_performance_ui();
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

static void publish_ready(void)
{
    int fd = open(READY_FILE, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0)
        return;
    (void)write(fd, "ready\n", 6);
    close(fd);
}

/* Sidecar loading. */

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

static int load_sidecar(const char *path, struct stem_payload *destination)
{
    memset(destination, 0, sizeof(*destination));
    int fd = open(path, O_RDONLY);
    if (fd < 0) {
        log_line("rejected: sidecar is not readable");
        return -1;
    }

    off_t size = lseek(fd, 0, SEEK_END);
    if (size < (off_t)sizeof(struct sidecar_header) || lseek(fd, 0, SEEK_SET) != 0) {
        close(fd);
        log_line("rejected: sidecar is truncated");
        return -1;
    }

    struct sidecar_header header;
    if (read_exactly(fd, &header, sizeof(header))) {
        close(fd);
        log_line("rejected: sidecar header is unreadable");
        return -1;
    }

    unsigned int frame_size;
    if (header.format == FORMAT_F32)
        frame_size = sizeof(Float2);
    else if (header.format == FORMAT_S16)
        frame_size = sizeof(Short2);
    else {
        close(fd);
        log_line("rejected: unknown format (1=float32, 2=int16)");
        return -1;
    }

    /* PcmReader uses a fixed 44,100 Hz internal time domain. */
    if (memcmp(header.magic, "RX3STM1", 7) || header.sample_rate != 44100 ||
        header.channels != 2 || header.header_size != sizeof(header) ||
        header.frames == 0 || header.frames > (0xffffffffu - sizeof(header)) / frame_size ||
        (uint64_t)header.header_size + header.frames * frame_size != (uint64_t)size) {
        close(fd);
        log_line("rejected: inconsistent sidecar header");
        return -1;
    }

    size_t payload = (size_t)(header.frames * frame_size);

    unsigned long available_kb = memory_available_kb();
    if (available_kb) {
        unsigned long needed_kb = (unsigned long)(payload >> 10);
        if (needed_kb > available_kb / MEM_DENOMINATOR * MEM_NUMERATOR) {
            close(fd);
            log_number("rejected: sidecar KiB required = ", needed_kb);
            log_number("          estimated KiB available = ", available_kb);
            return -1;
        }
    }

    void *block = mmap(0, payload, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (block == MAP_FAILED) {
        close(fd);
        log_line("rejected: anonymous RAM allocation failed");
        return -1;
    }

    if (read_exactly(fd, block, payload)) {
        munmap(block, payload);
        close(fd);
        log_line("rejected: incomplete sidecar read");
        return -1;
    }
    close(fd);

    /* Make the completed payload read-only. An accidental audio-thread write
       then fails explicitly instead of silently corrupting samples. */
    (void)mprotect(block, payload, PROT_READ);

    destination->block      = block;
    destination->block_size = payload;
    destination->data       = block;
    destination->format     = header.format;
    destination->frames     = header.frames;

    log_number("sidecar resident frames = ", (unsigned long)header.frames);
    log_number("sidecar resident KiB = ", (unsigned long)(payload >> 10));
    log_number("sidecar format = ", (unsigned long)header.format);
    return 0;
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
static int sidecar_path_for_track(const void *track_info, char *output,
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

static int sidecar_is_readable(const char *path)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0)
        return 0;
    close(fd);
    return 1;
}

static void *sidecar_loader(void *opaque)
{
    struct stems_load_request *request = opaque;
    struct stem_payload next;
    int loaded = !load_sidecar(request->path, &next);
    struct stems_deck_context *context = request->context;

    if (loaded && context->generation == request->generation &&
        context->reader == request->reader) {
        /* Temporarily remove the reader from the lookup table while publishing
           the payload. getStreamAt remains on the stock path until complete. */
        context->reader = 0;
        __sync_synchronize();
        release_payload(&context->vocal);
        context->vocal = next;
        __sync_synchronize();
        context->reader = request->reader;
        log_number("asynchronous sidecar ready on deck = ",
                   (unsigned long)(context - stems_decks) + 1u);
    } else {
        if (loaded)
            release_payload(&next);
        if (!loaded && context->generation == request->generation &&
            context->reader == request->reader)
            context->armed = 0;
        if (context->generation != request->generation)
            log_line("asynchronous sidecar discarded: track was replaced");
    }
    munmap(request, 4096u);
    return 0;
}

/* Hook installation. */

static void clear_instruction_cache(unsigned long first, unsigned long last)
{
    register unsigned long r0 __asm__("r0") = first;
    register unsigned long r1 __asm__("r1") = last;
    register unsigned long r2 __asm__("r2") = 0;
    register unsigned long r7 __asm__("r7") = 0x0f0002u; /* __ARM_NR_cacheflush */
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
}

static int write_code(unsigned long address, const void *bytes, size_t length)
{
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0)
        page_size = 4096;
    unsigned long mask  = (unsigned long)page_size - 1u;
    unsigned long first = address & ~mask;
    unsigned long last  = (address + length - 1u) & ~mask;
    size_t span = (size_t)(last - first) + (size_t)page_size;

    if (mprotect((void *)first, span, PROT_READ | PROT_WRITE))
        return -1;
    memcpy((void *)address, bytes, length);
    clear_instruction_cache(address, address + length);
    if (mprotect((void *)first, span, PROT_READ | PROT_EXEC))
        return -1;
    return 0;
}

static void uninstall_hook(struct installed_hook *hook)
{
    if (!hook->address)
        return;
    (void)write_code(hook->address, hook->original, sizeof(hook->original));
    if (hook->trampoline)
        munmap(hook->trampoline, 4096);
    memset(hook, 0, sizeof(*hook));
}

/*
 * Copy the first eight bytes into a trampoline and append an absolute jump to
 * address+8. These stolen instructions have no PC-relative dependency:
 *   getStreamAt : ldrb r12,[r0,#0x9c] ; stmdb sp!,{r4..r8,r10,lr}
 *   load        : stmdb sp!,{r4..r11,lr} ; sub sp,sp,#0x5c
 *   onKey_Pad   : ldrh r3,[r1,#8] ; stmdb sp!,{r4..r11,lr}
 */
static void *install_hook(struct installed_hook *hook, unsigned long address,
                          const uint8_t guard[8], void *replacement)
{
    if (memcmp((const void *)address, guard, 8))
        return 0;

    uint32_t *trampoline = mmap(0, 4096, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (trampoline == MAP_FAILED)
        return 0;
    memcpy(trampoline, (const void *)address, 8);
    trampoline[2] = 0xe51ff004;                      /* ldr pc,[pc,#-4] */
    trampoline[3] = (uint32_t)(address + 8);
    clear_instruction_cache((unsigned long)trampoline,
                            (unsigned long)trampoline + 16u);
    if (mprotect(trampoline, 4096, PROT_READ | PROT_EXEC)) {
        munmap(trampoline, 4096);
        return 0;
    }

    uint32_t patch[2] = {0xe51ff004, (uint32_t)(unsigned long)replacement};
    if (write_code(address, patch, sizeof(patch))) {
        munmap(trampoline, 4096);
        return 0;
    }

    hook->address = address;
    memcpy(hook->original, guard, sizeof(hook->original));
    hook->trampoline = trampoline;
    return trampoline;
}

#if defined(RX3_EMULATOR_BUILD)
#include "rx3_core_emulator_breadcrumbs.h"
#endif

/* Variant for ldr r3,[pc,#imm12] followed by push. The trampoline loads a copy
   of the original literal value, replays push, and joins address+8. This
   preserves r3 without depending on the shared object's mapped address. */
static void *install_pc_ldr_hook(struct installed_hook *hook,
                                 unsigned long address,
                                 const uint8_t guard[8], void *replacement)
{
    if (memcmp((const void *)address, guard, 8))
        return 0;

    uint32_t instruction = *(const uint32_t *)address;
    if ((instruction & 0xfffff000u) != 0xe59f3000u)
        return 0;
    unsigned long literal_address = address + 8u + (instruction & 0xfffu);
    uint32_t literal_value = *(const uint32_t *)literal_address;

    uint32_t *trampoline = mmap(0, 4096, PROT_READ | PROT_WRITE,
                                MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (trampoline == MAP_FAILED)
        return 0;
    trampoline[0] = 0xe59f3008u;                    /* ldr r3,[pc,#8] */
    trampoline[1] = *(const uint32_t *)(address + 4u); /* push original */
    trampoline[2] = 0xe51ff004u;                    /* ldr pc,[pc,#-4] */
    trampoline[3] = (uint32_t)(address + 8u);
    trampoline[4] = literal_value;
    clear_instruction_cache((unsigned long)trampoline,
                            (unsigned long)trampoline + 20u);
    if (mprotect(trampoline, 4096, PROT_READ | PROT_EXEC)) {
        munmap(trampoline, 4096);
        return 0;
    }

    uint32_t patch[2] = {0xe51ff004u, (uint32_t)(unsigned long)replacement};
    if (write_code(address, patch, sizeof(patch))) {
        munmap(trampoline, 4096);
        return 0;
    }

    hook->address = address;
    memcpy(hook->original, guard, sizeof(hook->original));
    hook->trampoline = trampoline;
    return trampoline;
}

/* Native overlay. NS_PALRender_DrawText receives a fully attached 0x54-byte
   NS_GlyphText. Clone a stock label from the pane the row stands in for, retain
   its window/parent, and alter only the public text-box fields established by
   NS_GlyphText_CreateFromProperty. Cloning is what carries the font: nothing
   below sets one, so the controls wear whichever face the model was drawn in. */

static const uint16_t text_empty[]    = {0};

#include "../../keyshift/1.19/rx3_keyshift_panel.h"
#include "../../stems/1.19/rx3_stems_panel.h"

static const struct rx3_panel_feature *panel_for_id(unsigned int panel_id)
{
    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++)
        if (runtime_features[i].active && runtime_features[i].panel &&
            runtime_features[i].panel->panel_id == panel_id)
            return runtime_features[i].panel;
    return 0;
}

static const struct rx3_panel_feature *panel_for_slot(unsigned int slot)
{
    if (slot >= RUNTIME_FEATURE_COUNT || !runtime_features[slot].active)
        return 0;
    return runtime_features[slot].panel;
}

static void set_u16(void *object, unsigned int offset, uint16_t value)
{
    memcpy((uint8_t *)object + offset, &value, sizeof(value));
}

static void set_u32(void *object, unsigned int offset, uint32_t value)
{
    memcpy((uint8_t *)object + offset, &value, sizeof(value));
}

static uint8_t text_length16(const uint16_t *text)
{
    uint8_t length = 0;
    while (text[length] && length < 0xfeu)
        length++;
    return length;
}

static void draw_native_box_local(void *render, const void *model,
                                  const void *window_model,
                                  uint8_t target_window,
                                  int x1, int y1, int x2, int y2,
                                  const uint16_t *label,
                                  uint32_t foreground, uint32_t background)
{
    uint8_t box[0x54];
    uint16_t window_layer;
    memcpy(box, model, sizeof(box));
    memcpy(&window_layer, (const uint8_t *)window_model + 0x10u,
           sizeof(window_layer));
    window_layer = (uint16_t)((window_layer & 0xff00u) | target_window);
    set_u16(box, 0x10, window_layer);
    set_u16(box, 0x18, (uint16_t)x1);
    set_u16(box, 0x1a, (uint16_t)y1);
    set_u16(box, 0x1c, (uint16_t)x2);
    set_u16(box, 0x1e, (uint16_t)y2);
    set_u32(box, 0x28, foreground);
    set_u32(box, 0x34, (uint32_t)(unsigned long)label);
    box[0x38] = text_length16(label);
    box[0x3c] = 4;
    set_u32(box, 0x40, 1);
    set_u32(box, 0x44, background);
    set_u32(box, 0x50, 1);
    original_draw_text(render, box);
}

/* Zero means "leave the cloned model's own colour alone", which is why these
   are still zero: the stock palette is known -- frame 0x632c, selected fill
   0x7bef, black inactive, measured off the stock tab strip -- but
   the encoding this field wants is not.
   NS_PALRender_DrawText decodes +0x44 three different ways depending on the
   window's pixel format, which it reads from DS_GR_GetWindowInfo, not from the
   glyph: format 2 takes the low byte alone, format 3 the whole word, format 9
   unpacks 0x00BBGGRR into 5/6/5. Feeding it RGB888 painted magenta lettering on
   green; feeding it RGB565 painted green; sweeping all 256 low-byte values
   moved the green channel alone and never once lifted red or blue off zero.
   So this window is not in a format where the field carries a colour we can
   write. Settling it means identifying the format DS_GR_GetWindowInfo reports
   for layers 0x17xx/0x18xx and using that branch's encoding -- until then,
   inheriting is honest and the earlier "every literal guess looked foreign" is
   explained rather than repeated. */
static void pioneer_theme(uint16_t window_layer,
                          uint32_t *border, uint32_t *inactive,
                          uint32_t *active, uint32_t *light_text)
{
    (void)window_layer;
    *border = 0x00000000u;
    *inactive = 0x00000000u;
    *active = 0x00000000u;
    *light_text = 0x00000000u;
}

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
    }
}


/* The tab strip. The stock STATUS / BEAT FX row is captured as it goes past --
   see the image id below -- and redrawn at the KEY / STEMS position, so the
   frame, the corner radius and the palette are rbp's own rather than a
   reconstruction. Drawing the boxes by hand was tried and rejected: the theme
   colours are not exposed, and every literal guess looked foreign. */
static void draw_custom_tabs(void *render, const void *image)
{
    overlay_seen_us = monotonic_enough_us();
    if (!stock_tab_backing_ready) {
        original_draw_image(render, (void *)image);
        return;
    }
    uint16_t window_layer;
    memcpy(&window_layer, (const uint8_t *)image + 0x10u, sizeof(window_layer));

    uint8_t backing[0x54];
    memcpy(backing, stock_tab_backing, sizeof(backing));
    if (tab_assets_ready) {
        const struct rx3_panel_feature *panel = panel_for_id(overlay_panel);
        uint32_t image_id = panel ? panel->tab_image : TAB_IMAGE_KEY_NONE;
        set_u32(backing, 0x44, image_id);
    }
    set_u16(backing, 0x10, window_layer);
    set_u16(backing, 0x18, 10u);
    set_u16(backing, 0x1a, 0u);
    set_u16(backing, 0x1c, 190u);
    set_u16(backing, 0x1e, 50u);
    original_draw_image(render, backing);
    custom_tab_draws++;
#if defined(RX3_EMULATOR_BUILD)
    if (custom_tab_draws == 1u)
        log_line("emulator custom tab rendered");
#endif
}

/* The face the controls are cut from. A pad label carries the row's own font;
   the header glyph is twice its size and is only a last resort, so a panel
   opened before any stock label was drawn still shows something. */
static const void *pad_button_face(void)
{
    return pad_text_template_ready ? pad_text_template : text_template;
}

static void draw_stock_button_local(void *render, const void *model,
                                    uint8_t window, int x1, int y1,
                                    int x2, int y2,
                                    const uint16_t *label, int selected,
                                    int pressed)
{
    uint16_t window_layer;
    memcpy(&window_layer, (const uint8_t *)model + 0x10u,
           sizeof(window_layer));
    window_layer = (uint16_t)((window_layer & 0xff00u) | window);
    uint32_t border, inactive, active, light_text;
    pioneer_theme(window_layer, &border, &inactive, &active, &light_text);
    const uint32_t dark_text = 0x00000000u;
    const void *face = pad_button_face();
    /* Held moves the fill one step towards the frame, which reads as pressed
       without resizing the button -- the stock idiom on this panel. */
    uint32_t fill = selected ? active : inactive;
    if (pressed)
        fill = selected ? border : active;
    draw_native_box_local(render, face, model, window,
                          x1, y1, x2, y2, text_empty,
                          light_text, border);
    draw_native_box_local(render, face, model, window,
                          x1 + 2, y1 + 2, x2 - 2, y2 - 2, label,
                          selected ? dark_text : light_text, fill);
}

static void draw_custom_pad_half(void *render, const void *model,
                                 uint8_t window, unsigned int deck)
{
    custom_pad_draws++;
#if defined(RX3_EMULATOR_BUILD)
    if (custom_pad_draws == 1u)
        log_line("emulator custom PAD rendered");
#endif
    const struct rx3_panel_feature *panel = panel_for_id(overlay_panel);
    if (!panel)
        return;
    for (unsigned int control = 0; control < panel->control_count; control++) {
        int pressed = (int)deck == pressed_deck &&
                      (int)control == pressed_control;
        draw_stock_button_local(
            render, model, window,
            panel->lefts[control], 21, panel->rights[control], 59,
            panel->label(deck, control), panel->selected(deck, control),
            pressed);
    }
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
   RX3_EMULATOR_FONT_DONOR names a subtree byte so candidates can be compared by
   looking at them; 0 keeps the original behaviour of waiting for a pad label
   that never comes. */
static unsigned int font_donor_subtree(void)
{
    static int donor = -1;
    if (donor < 0) {
        const char *requested = getenv("RX3_EMULATOR_FONT_DONOR");
        donor = 0;
        if (requested)
            for (const char *c = requested; *c >= '0' && *c <= '9'; c++)
                donor = donor * 10 + (*c - '0');
    }
    return (unsigned int)donor;
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
    /* Selecting a donor by layer picked four faces that all render at 19 px,
       because a layer draws text at more than one size. Selecting by measured
       box height searches the actual range instead. */
    static int ceiling = -1;
    if (ceiling < 0) {
        const char *requested = getenv("RX3_EMULATOR_FONT_MAXH");
        ceiling = 0;
        if (requested)
            for (const char *c = requested; *c >= '0' && *c <= '9'; c++)
                ceiling = ceiling * 10 + (*c - '0');
        if (!ceiling)
            ceiling = 64;
    }
    if (height < 8 || height > ceiling)
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

static void hooked_draw_image(void *render, void *image)
{
    image_draw_calls++;
    if (RX3_DIAGNOSTIC_ONLY) {
        original_draw_image(render, image);
        return;
    }
    /* Populate the private image records before their first DirectFB lookup.
       Pioneer image-table records and their cached surfaces stay untouched. */
    if (!tab_assets_ready)
        install_tab_assets();
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

    /* Capture the native 180x50 model, including its renderer/window
       attachment. While a custom panel is selected, replace the stock row by
       the no-selection artwork: STATUS and BEAT FX are then both black even
       though rbp internally remains in BEAT FX so its pad subtree stays live. */
    if (window_layer == PERFORMANCE_TAB_LAYER &&
        (image_id == 0x1598u || image_id == 0x1599u)) {
        stock_status_glyph = image;
        memcpy(stock_tab_backing, image, sizeof(stock_tab_backing));
        stock_tab_backing_ready = 1u;
        refresh_initial_performance_tabs_if_ready();
        if (overlay_panel && tab_assets_ready) {
            uint8_t neutral[0x54];
            memcpy(neutral, image, sizeof(neutral));
            set_u32(neutral, 0x44, TAB_IMAGE_STATUS_NONE);
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
            if (pad_text_template_ready || text_template_ready)
                draw_custom_pad_half(render, image, window,
                                     deck_for_pad_subtree(window_layer));
        }
        return;
    }

    if (image_id != 0x15c9u && image_id != 0x15cau) {
        original_draw_image(render, image);
        return;
    }
    if (!text_template_ready) {
        original_draw_image(render, image);
        return;
    }

    draw_custom_tabs(render, image);
}

#if defined(RX3_EMULATOR_BUILD)
/* Which window layers actually issue a text draw.
   The pad-label template has never been captured, and the reason matters: if
   the pad subtree draws no text at all then the row is images and cloning a
   label is the wrong approach entirely. Bounded to one line per distinct layer
   and a hard ceiling -- an earlier unbounded version of this flooded the log
   and took DirectFB down with it. */
static void note_text_layer(uint16_t window_layer, const void *text)
{
    static uint16_t seen[48];
    static unsigned int seen_count;
    /* Read once. This sits in the render path, and calling getenv per draw
       walks the environment thousands of times a second -- enough on its own
       to stop DirectFB coming up, which is how the first version of this probe
       announced itself. */
    static int enabled = -1;
    if (enabled < 0) {
        const char *requested = getenv("RX3_EMULATOR_TRACE_LAYERS");
        enabled = requested && requested[0] == '1';
    }
    if (!enabled || seen_count >= 48u)
        return;
    for (unsigned int i = 0; i < seen_count; i++)
        if (seen[i] == window_layer)
            return;
    seen[seen_count++] = window_layer;
    {
        uint16_t y1, y2;
        memcpy(&y1, (const uint8_t *)text + 0x1au, sizeof(y1));
        memcpy(&y2, (const uint8_t *)text + 0x1eu, sizeof(y2));
        /* Layer and box height together: the header face is twice a stock pad
           label, so height is what identifies a usable donor glyph. */
        log_number("text layer ", (unsigned long)window_layer);
        log_number("   box height = ", (unsigned long)(uint16_t)(y2 - y1));
    }
}
#endif

static void hooked_draw_text(void *render, void *text)
{
    draw_calls++;
    uint16_t window_layer;
    memcpy(&window_layer, (const uint8_t *)text + 0x10u, sizeof(window_layer));
#if defined(RX3_EMULATOR_BUILD)
    note_text_layer(window_layer, text);
#endif
    if (!RX3_DIAGNOSTIC_ONLY)
        capture_pad_text_template(text, window_layer);
    /* The row is painted from the pane backdrop, so a stock label inside the
       subtree is simply dropped once it has been cloned. */
    if (!RX3_DIAGNOSTIC_ONLY && overlay_panel &&
        is_performance_pad_subtree(window_layer))
        return;
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

static int native_touch_index(const void *area)
{
    for (unsigned int i = 0; i < 6u; i++)
        if (beatfx_touch_areas[i] == area)
            return (int)i;
    return -1;
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

static void configure_native_performance_touches(unsigned int panel)
{
    if (!beatfx_touch_areas[0])
        return;
    const struct rx3_panel_feature *feature = panel_for_id(panel);
    if (feature) {
        for (unsigned int deck = 0; deck < 2u; deck++)
            for (unsigned int control = 0;
                 control < feature->control_count; control++) {
                unsigned int index = deck * feature->control_count + control;
                unsigned int width = (unsigned int)(
                    feature->rights[control] - feature->lefts[control] + 1);
                set_touch_geometry(beatfx_touch_areas[index],
                                   (int)(deck * 640u) + feature->lefts[control],
                                   521, width, 39u);
            }
        for (unsigned int i = feature->control_count * 2u; i < 6u; i++)
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

static void restore_status_after_pad_mode(void)
{
    if (!overlay_panel)
        return;
    overlay_panel = 0;
    captured_native_touch = 0;
    pressed_deck = -1;
    pressed_control = -1;
    configure_native_performance_touches(0);
    if (original_set_beatfx_selected)
        original_set_beatfx_selected(0);
    refresh_performance_ui();
    log_line("pad mode selected: custom panel returned to STATUS");
}

static int pad_mode_key_pressed(const void *key_input)
{
    return (*(const uint8_t *)((const uint8_t *)key_input + 0x0bu) & 0x0fu) == 0u;
}

static int hooked_on_key_hot_cue(void *player_innards, const void *key_input)
{
    int result = original_on_key_hot_cue(player_innards, key_input);
    if (pad_mode_key_pressed(key_input))
        restore_status_after_pad_mode();
    return result;
}

static int hooked_on_key_beat_loop(void *player_innards, const void *key_input)
{
    int result = original_on_key_beat_loop(player_innards, key_input);
    if (pad_mode_key_pressed(key_input))
        restore_status_after_pad_mode();
    return result;
}

static int hooked_on_key_slip_loop(void *player_innards, const void *key_input)
{
    int result = original_on_key_slip_loop(player_innards, key_input);
    if (pad_mode_key_pressed(key_input))
        restore_status_after_pad_mode();
    return result;
}

static int hooked_on_key_beat_jump(void *player_innards, const void *key_input)
{
    int result = original_on_key_beat_jump(player_innards, key_input);
    if (pad_mode_key_pressed(key_input))
        restore_status_after_pad_mode();
    return result;
}

static void *hooked_beatfx_xpad_ctor(void *object, void *notification)
{
    void *result = original_beatfx_xpad_ctor(object, notification);
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
    configure_native_performance_touches(overlay_panel);
    log_line("native BeatFxAndXPad touch areas captured");
    return result;
}

static void activate_native_performance_touch(void *area)
{
    int index = native_touch_index(area);
    const struct rx3_panel_feature *panel = panel_for_id(overlay_panel);
    if (index < 0 || !panel)
        return;
    if ((unsigned int)index >= panel->control_count * 2u)
        return;
    captured_native_touch = area;
    unsigned int deck = (unsigned int)index / panel->control_count;
    unsigned int control = (unsigned int)index % panel->control_count;
    /* Held before the action, so the repaint the action asks for already
       carries the pressed fill. */
    pressed_deck = (int)deck;
    pressed_control = (int)control;
    panel->activate(deck, control);
    log_number("native feature touch = ", (unsigned long)index);

    /* KEY/STEMS controls stay in their panel so successive adjustments remain
       visible. Only a hardware pad-mode selector restores STATUS. */
    refresh_performance_ui();
}

/* The release edge. Without the repaint the button would stay lit until some
   other invalidation happened along, which is why holding felt like nothing. */
static void release_native_performance_touch(void)
{
    captured_native_touch = 0;
    if (pressed_deck < 0)
        return;
    pressed_deck = -1;
    pressed_control = -1;
    refresh_performance_ui();
}

static void hooked_touch_button_on(void *area)
{
    if (native_touch_index(area) >= 0 && overlay_panel) {
        activate_native_performance_touch(area);
        return;
    }
    original_touch_button_on(area);
}

static void hooked_touch_button_hold(void *area, unsigned int x, unsigned int y)
{
    if (area == captured_native_touch ||
        (native_touch_index(area) >= 0 && overlay_panel))
        return;
    original_touch_button_hold(area, x, y);
}

static void hooked_touch_button_off(void *area)
{
    if (area == captured_native_touch ||
        (native_touch_index(area) >= 0 && overlay_panel)) {
        release_native_performance_touch();
        return;
    }
    original_touch_button_off(area);
}

static void hooked_touch_toggle_on(void *area)
{
    if (native_touch_index(area) >= 0 && overlay_panel) {
        activate_native_performance_touch(area);
        return;
    }
    original_touch_toggle_on(area);
}

static void hooked_touch_toggle_off(void *area)
{
    if (area == captured_native_touch ||
        (native_touch_index(area) >= 0 && overlay_panel)) {
        release_native_performance_touch();
        return;
    }
    original_touch_toggle_off(area);
}

static void hooked_touch_xpad_on(void *area)
{
    if (native_touch_index(area) >= 0 && overlay_panel) {
        activate_native_performance_touch(area);
        return;
    }
    original_touch_xpad_on(area);
}

static void hooked_touch_xpad_off(void *area)
{
    if (area == captured_native_touch ||
        (native_touch_index(area) >= 0 && overlay_panel)) {
        release_native_performance_touch();
        return;
    }
    original_touch_xpad_off(area);
}

static void hooked_touch_xpad_hold(void *area, unsigned int x, unsigned int y)
{
    if (area == captured_native_touch ||
        (native_touch_index(area) >= 0 && overlay_panel))
        return;
    original_touch_xpad_hold(area, x, y);
}

static void select_custom_panel(unsigned int panel)
{
    beatfx_reselect_pending = 0u;
    (void)__sync_add_and_fetch(&beatfx_reselect_generation, 1u);
    overlay_panel = panel;
    /* BeatFxAndXPad is dispatched only while the firmware's binary state is
       BEAT FX. Keep that state active for the lifetime of the custom panel;
       STATUS and BEAT FX physical keys leave it through the hooked setter. */
    if (original_set_beatfx_selected)
        original_set_beatfx_selected(1);
    configure_native_performance_touches(panel);
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
#if defined(RX3_EMULATOR_BUILD)
    if (emulator_forced_panel && emulator_panel_applied) {
        overlay_panel = emulator_forced_panel;
        original_set_beatfx_selected(1);
        return;
    }
#endif
    unsigned int leaving_custom_panel = overlay_panel != 0u;
    overlay_panel = 0;
    captured_native_touch = 0;
    configure_native_performance_touches(0);
    /* Ui_CycleTask can echo the provisional STATUS value through this setter.
       While the two-cycle transition is pending, neither that internal 0 nor
       duplicate 1 stores may alter the generation. A new KEY/STEMS selection
       cancels explicitly in select_custom_panel(). */
    if (beatfx_reselect_pending) {
        log_number("native Beat FX rebuild ignored setter = ",
                   (unsigned long)selected);
        return;
    }
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

#if defined(RX3_EMULATOR_BUILD)
#include "rx3_core_emulator_harness.h"
#endif

static void hooked_solve_touch(void *handler, const void *status,
                               const void *mode)
{
    touch_calls++;
#if defined(RX3_EMULATOR_BUILD)
    /* The probe counters are dumped once per run, so they can never show
       whether a touch injected later arrived. This says so the moment it does,
       and only the first time, because this is rbp's hot touch path. */
    {
        static volatile unsigned int announced;
        if (!announced) {
            announced = 1u;
            log_line("native solveCoordToKey reached");
        }
    }
#endif
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

    if (captured_touch) {
        *(uint8_t *)((uint8_t *)handler + 4u) = (uint8_t)pressed;
        *(int *)((uint8_t *)handler + 8u) = x;
        *(int *)((uint8_t *)handler + 0xcu) = y;
        if (!pressed)
            captured_touch = 0;
        return;
    }

    if (pressed && !*(const uint8_t *)((const uint8_t *)handler + 4u) &&
        performance_overlay_is_visible()) {
        const struct rx3_panel_feature *left = panel_for_slot(0u);
        const struct rx3_panel_feature *right = panel_for_slot(1u);
        if (left && point_in_rect(x, y, 1090, 363, 1179, 413)) {
            select_custom_panel(left->panel_id);
            log_line("touch action = left feature panel");
            captured_touch = 3u;
        } else if (right && point_in_rect(x, y, 1181, 363, 1270, 413)) {
            select_custom_panel(right->panel_id);
            log_line("touch action = right feature panel");
            captured_touch = 3u;
        }
        if (captured_touch) {
            *(uint8_t *)((uint8_t *)handler + 4u) = 1;
            *(int *)((uint8_t *)handler + 8u) = x;
            *(int *)((uint8_t *)handler + 0xcu) = y;
            return;
        }
    }
    original_solve_touch(handler, status, mode);
}

/* Audio mixing. */

static struct stems_deck_context *context_for_reader(const void *reader)
{
    int deck = deck_index_for_reader(reader);
    if (deck < 0 || stems_decks[deck].reader != reader)
        return 0;
    return &stems_decks[deck];
}

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

static Float2 vocal_at(const struct stems_deck_context *context,
                       unsigned long index)
{
    Float2 sample;
    if (context->vocal.format == FORMAT_S16) {
        const Short2 *source = (const Short2 *)context->vocal.data + index;
        sample.left  = (float)source->left  * (1.0f / 32768.0f);
        sample.right = (float)source->right * (1.0f / 32768.0f);
    } else {
        sample = ((const Float2 *)context->vocal.data)[index];
    }
    return sample;
}

static Float2 sample_for_mode(Float2 full, Float2 vocal, enum stem_mode selected)
{
    if (selected == MODE_NONE) {
        Float2 silence = {0.0f, 0.0f};
        return silence;
    }
    if (selected == MODE_VOCAL)
        return vocal;
    if (selected == MODE_INSTRUMENTAL) {
        Float2 instrumental = {full.left - vocal.left, full.right - vocal.right};
        return instrumental;
    }
    return full;
}

/* An all-zero block represents an unbuffered region filled by getStreamAt.
   Leave it unchanged. */
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
}

static void apply_mix(struct stems_deck_context *context,
                      unsigned long position, Float2 *output,
                      unsigned long frames, enum stem_mode selected)
{
    if (selected != context->transition_to) {
        context->transition_from   = context->rendered_mode;
        context->transition_to     = selected;
        context->transition_cursor = 0;
    }

    if (context->transition_cursor >= TRANSITION_FRAMES) {
        context->rendered_mode = selected;
        if (selected == MODE_BOTH)
            return;
        for (unsigned long i = 0; i < frames; i++) {
            if (output[i].left == 0.0f && output[i].right == 0.0f)
                continue;
            output[i] = sample_for_mode(output[i], vocal_at(context, position + i), selected);
        }
        return;
    }

    for (unsigned long i = 0; i < frames; i++) {
        Float2 full  = output[i];
        /* A call may be partially zero-filled. Never turn a stock zero frame
           into vocal audio or inverted vocal audio. */
        if (full.left == 0.0f && full.right == 0.0f)
            continue;
        Float2 vocal = vocal_at(context, position + i);
        Float2 destination = sample_for_mode(full, vocal, context->transition_to);
        if (context->transition_cursor < TRANSITION_FRAMES) {
            Float2 source = sample_for_mode(full, vocal, context->transition_from);
            float alpha = (float)(context->transition_cursor + 1u) / (float)TRANSITION_FRAMES;
            output[i].left  = source.left  + (destination.left  - source.left)  * alpha;
            output[i].right = source.right + (destination.right - source.right) * alpha;
            context->transition_cursor++;
            if (context->transition_cursor == TRANSITION_FRAMES)
                context->rendered_mode = context->transition_to;
        } else {
            output[i] = destination;
        }
    }
}

#include "../../keyshift/1.19/rx3_keyshift.h"

/* Shared hook replacement. Feature-specific hooks are composed below. */
#include "../../keyshift/1.19/rx3_keyshift_feature.h"
#include "../../stems/1.19/rx3_stems_feature.h"

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

    int result = original_load(reader, track_info);
    __sync_synchronize();
    deck_readers[channel] = reader;
    __sync_synchronize();

    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++)
        if (runtime_features[i].active && runtime_features[i].track_did_load)
            runtime_features[i].track_did_load(channel, reader, track_info);
    return result;
}

static unsigned int configure_features(void)
{
    unsigned int active = 0;
    for (unsigned int i = 0; i < RUNTIME_FEATURE_COUNT; i++) {
        runtime_features[i].active = runtime_features[i].configured &&
                                     runtime_features[i].configured();
        if (runtime_features[i].active)
            active++;
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
        if (!feature->install || feature->install()) {
            active++;
            continue;
        }
        log_line("optional feature disabled: hook guard rejected");
        log_line(feature->name);
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
    configure_native_performance_touches(0);
    remove_features();
    uninstall_hook(&touch_xpad_hold_hook);
    uninstall_hook(&touch_xpad_off_hook);
    uninstall_hook(&touch_xpad_on_hook);
    uninstall_hook(&touch_toggle_off_hook);
    uninstall_hook(&touch_toggle_on_hook);
    uninstall_hook(&touch_button_off_hook);
    uninstall_hook(&touch_button_hold_hook);
    uninstall_hook(&touch_button_on_hook);
    uninstall_hook(&beatfx_xpad_ctor_hook);
    uninstall_hook(&beat_jump_hook);
    uninstall_hook(&slip_loop_hook);
    uninstall_hook(&beat_loop_hook);
    uninstall_hook(&hot_cue_hook);
    uninstall_hook(&set_beatfx_hook);
    uninstall_hook(&touch_hook);
    uninstall_hook(&draw_image_hook);
    uninstall_hook(&draw_text_hook);
    uninstall_hook(&load_hook);
}

__attribute__((constructor)) static void initialize(void)
{
    /* Each feature is a module of its own and announces itself through the
       environment its module.sh exports. The core installs either way, so that
       key shift works without sidecars and stems works without key shift. */
#if defined(RX3_EMULATOR_BUILD)
    /* Before anything else, and before the feature gate below: init() runs
       whether or not a feature is selected, so both of these have to be
       installable independently of one -- and the latch has to be in place
       before rbp constructs the deck objects it captures. */
    install_player_innards_latch();
    install_init_breadcrumbs();
#endif
    stems_dir = getenv("RX3_STEMS_DIR");
    if (stems_dir && !stems_dir[0])
        stems_dir = 0;
    const char *keyshift = getenv("RX3_KEYSHIFT");
    keyshift_enabled = keyshift && keyshift[0] == '1';
    if (!configure_features()) {
        /* Nothing selected: leave rbp exactly as it is. */
        return;
    }

    for (unsigned int i = 0; i < 2u; i++) {
        stems_decks[i].mode = MODE_BOTH;
        stems_decks[i].rendered_mode = MODE_BOTH;
        stems_decks[i].transition_from = MODE_BOTH;
        stems_decks[i].transition_to = MODE_BOTH;
        stems_decks[i].transition_cursor = TRANSITION_FRAMES;
    }

    /* PcmReader::load is the core deck-identity service used independently by
       both features. The remaining audio/pad hooks belong to stems alone. */
    original_load = (load_fn)install_hook(
        &load_hook, PCM_LOAD, load_guard, (void *)hooked_load);
    if (!original_load) {
        log_line("rejected: unexpected PcmReader::load prologue");
        return;
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

    original_beatfx_xpad_ctor = (beatfx_xpad_ctor_fn)install_hook(
        &beatfx_xpad_ctor_hook, BEATFX_XPAD_CTOR, beatfx_xpad_ctor_guard,
        (void *)hooked_beatfx_xpad_ctor);
    if (!original_beatfx_xpad_ctor) {
        log_line("rejected: unexpected BeatFxAndXPad constructor prologue");
        goto reject_performance_hooks;
    }

    original_touch_button_on = (touch_area_fn)install_hook(
        &touch_button_on_hook, TOUCH_BUTTON_ON, touch_button_on_guard,
        (void *)hooked_touch_button_on);
    original_touch_button_hold = (touch_area_hold_fn)install_hook(
        &touch_button_hold_hook, TOUCH_BUTTON_HOLD, touch_button_hold_guard,
        (void *)hooked_touch_button_hold);
    original_touch_button_off = (touch_area_fn)install_hook(
        &touch_button_off_hook, TOUCH_BUTTON_OFF, touch_button_off_guard,
        (void *)hooked_touch_button_off);
    original_touch_toggle_on = (touch_area_fn)install_hook(
        &touch_toggle_on_hook, TOUCH_TOGGLE_ON, touch_toggle_on_guard,
        (void *)hooked_touch_toggle_on);
    original_touch_toggle_off = (touch_area_fn)install_hook(
        &touch_toggle_off_hook, TOUCH_TOGGLE_OFF, touch_toggle_off_guard,
        (void *)hooked_touch_toggle_off);
    original_touch_xpad_on = (touch_area_fn)install_hook(
        &touch_xpad_on_hook, TOUCH_XPAD_ON, touch_xpad_on_guard,
        (void *)hooked_touch_xpad_on);
    original_touch_xpad_off = (touch_area_fn)install_hook(
        &touch_xpad_off_hook, TOUCH_XPAD_OFF, touch_xpad_off_guard,
        (void *)hooked_touch_xpad_off);
    original_touch_xpad_hold = (touch_area_hold_fn)install_hook(
        &touch_xpad_hold_hook, TOUCH_XPAD_HOLD, touch_xpad_hold_guard,
        (void *)hooked_touch_xpad_hold);
    if (!original_touch_button_on || !original_touch_button_hold ||
        !original_touch_button_off || !original_touch_toggle_on ||
        !original_touch_toggle_off || !original_touch_xpad_on ||
        !original_touch_xpad_off || !original_touch_xpad_hold) {
        log_line("rejected: unexpected native performance touch prologue");
        goto reject_performance_hooks;
    }

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

    if (!install_features())
        goto reject_performance_hooks;

#if defined(RX3_EMULATOR_BUILD)
    /* The host has no front-panel microcontroller to request the first native
       transition. Force one configured panel so the real rendering branches
       are observable and clickable. */
    const char *emulator_panel = getenv("RX3_EMULATOR_PANEL");
    if (emulator_panel &&
        (emulator_panel[0] == '1' || emulator_panel[0] == '2')) {
        unsigned int requested = (unsigned int)(emulator_panel[0] - '0');
        if (panel_for_id(requested)) {
            emulator_forced_panel = requested;
            log_number("emulator requested feature panel = ", requested);
        }
    }
#endif

    state_thread_running = 1;
    pthread_t state_thread;
    if (!pthread_create(&state_thread, 0, watch_patch_state, 0))
        pthread_detach(state_thread);
    else
        log_line("warning: patch-state watcher could not start");
#if defined(RX3_EMULATOR_BUILD)
    pthread_t touch_thread;
    if (!pthread_create(&touch_thread, 0, emulator_touch_loop, 0))
        pthread_detach(touch_thread);
    else
        log_line("warning: emulator touch thread could not start");
#endif
    publish_ready();
    log_line("RX3 performance hook active: native ZOOM/GRID replacement and wait caution");
    return;

reject_performance_hooks:
    uninstall_performance_hooks();
    original_touch_xpad_hold = 0;
    original_touch_xpad_off = 0;
    original_touch_xpad_on = 0;
    original_touch_toggle_off = 0;
    original_touch_toggle_on = 0;
    original_touch_button_off = 0;
    original_touch_button_hold = 0;
    original_touch_button_on = 0;
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
    state_thread_running = 0;
    uninstall_performance_hooks();
    for (unsigned int i = 0; i < 2u; i++) {
        for (unsigned int feature = 0;
             feature < RUNTIME_FEATURE_COUNT; feature++)
            if (runtime_features[feature].destroy_deck)
                runtime_features[feature].destroy_deck(i);
    }
}
