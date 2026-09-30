/* SPDX-License-Identifier: MPL-2.0
 * Light theme policy, private to rx3_theme_module.c. The module decides what
 * is chrome, how pixels convert and when to switch; the core's image service
 * owns both tables and the fill adapter, and its input service owns SHIFT.
 */

#ifndef RX3_THEME_FEATURE_H
#define RX3_THEME_FEATURE_H

static int theme_enabled;
static struct installed_hook theme_render_pass_hook;
static void (*original_theme_render_pass)(void *manager);
static int theme_render_pass_installed;
static int theme_key_registered;

/* Converted pixels live in one arena the module allocates once and keeps for
 * the life of the process: published records keep pointing into it.
 */
static uint8_t *theme_arena;
static size_t theme_arena_used;
static int theme_run_conversions(void);
static unsigned int theme_render_active;
static uint8_t theme_id_done[(STOCK_IMAGE_COUNT + 7u) / 8u];
static const uint16_t *theme_seen_source[4096];
static const uint16_t *theme_seen_pixels[4096];
static unsigned int theme_seen_count;

static int theme_light_active(void)
{
    return framework->images->light_active();
}

static unsigned int theme_fill_channel(unsigned int fill, unsigned int shift)
{
    unsigned int channel = fill >> shift;
    /* Green is six bits where the others are five. Comparing the three means
       putting them on one scale first, and down is the only direction that
       cannot invent precision. */
    if (shift == THEME_FILL_GREEN_SHIFT)
        channel >>= 1;
    return channel & 0x1fu;
}

#include "rx3_theme_pixels.h"

/* Whether this fill colour is chrome rather than a decision.
 *
 * A dark neutral is the background the stock interface is built out of, and
 * replacing it is the whole theme. A bright fill, or one with any spread
 * across its channels, is carrying meaning: a status, a warning, the edge of
 * an artwork. Those are left exactly as they are.
 */
static int theme_fill_is_chrome(unsigned int fill)
{
    unsigned int red = theme_fill_channel(fill, THEME_FILL_RED_SHIFT);
    unsigned int green = theme_fill_channel(fill, THEME_FILL_GREEN_SHIFT);
    unsigned int blue = theme_fill_channel(fill, THEME_FILL_BLUE_SHIFT);
    unsigned int high = red > green ? red : green;
    unsigned int low = red < green ? red : green;
    if (blue > high)
        high = blue;
    if (blue < low)
        low = blue;
    return high < THEME_FILL_MAX_CHANNEL || high - low <= THEME_FILL_MAX_SPREAD;
}

/* Ground or panel, decided by the shape of the rectangle being filled.
 *
 * The panes that make up the whole screen keep the ground; everything drawn on
 * top of them, and everything too small to be a pane, takes the lighter panel
 * colour. The dimensions are the ones the player uses and are not derivable
 * from anything: they were read off a build.
 */
static unsigned int theme_fill_for_rect(unsigned int width, unsigned int height)
{
    if (width * height < THEME_PANE_MIN_AREA)
        return THEME_FILL_PANEL;
    if (width == THEME_PANE_WIDE && height == THEME_PANE_TALL)
        return THEME_FILL_PANEL;
    if (width == THEME_PANE_MID && height == THEME_PANE_MEDIUM)
        return THEME_FILL_PANEL;
    if ((width == THEME_PANE_WIDE || width == THEME_PANE_NARROW) &&
        height == THEME_PANE_LOW)
        return THEME_FILL_PANEL;
    if (width == THEME_PANE_SHORT && height == THEME_PANE_SHALLOW)
        return THEME_FILL_PANEL;
    return THEME_FILL_GROUND;
}

/* The core calls this for solid fills while the light table is shown. */
static unsigned int theme_fill(unsigned int colour, unsigned int width, unsigned int height)
{
    return theme_fill_is_chrome(colour) ? theme_fill_for_rect(width, height) : colour;
}

/* Set when a SHORTCUT press was taken for the combination, so its release is
   taken too. Without it the player sees a key come up that never went down. */
static uint8_t theme_shortcut_swallowed;
/* Set when the combination has been seen and the mode has not been flipped
 * yet. The flip itself does not happen on the key path: that runs inside the
 * player's own input handling, and repainting the whole interface from there
 * is how a key press turns into a dropped frame.
 */
static volatile int theme_toggle_pending;
static unsigned int theme_refresh_pending;
/* The light theme can start armed rather than active. The player paints its
   own first frame stock, and the display is taken over only once it has:
   switching during that first paint is what leaves half the chrome in one
   theme and half in the other, and it is not recoverable without a toggle. */
static int theme_light_armed;
static uint64_t theme_start_light_not_before_us;
#include "rx3_theme_utility.h"

static void theme_waveform_apply(int light);

/* Watch for SHIFT + SHORTCUT and swallow the SHORTCUT that completes it.
 *
 * Swallowing matters. SHORTCUT on its own is a stock function, and letting it
 * through as well would mean the display mode and whatever that function does
 * both happen on one press. The release is swallowed too, or the player is left
 * believing a key it never saw pressed has just come up.
 */
static int theme_key(const struct rx3_key_event *event)
{
    if (event->key != THEME_KEY_SHORTCUT)
        return 0;
    /* SHIFT is reported per deck, on channels 1 and 2. SHORTCUT belongs to
       the unit and arrives on channel 0, so its own channel never holds the
       modifier. Either deck's SHIFT completes the combination, which is also
       what the hand does: one is pressed on whichever side is free. */
    if (event->operation == THEME_KEY_PRESS && framework->input->shift_held(RX3_NO_DECK)) {
        theme_shortcut_swallowed = 1u;
        __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 1);
        return 1;
    }
    if ((event->operation & ~1u) == THEME_KEY_RELEASE && theme_shortcut_swallowed) {
        theme_shortcut_swallowed = 0u;
        return 1;
    }
    return 0;
}

/* Called at the render-pass boundary, before the native queue is consumed.
   Changing the table from a per-glyph callback mixes two themes in one pass.
   The key and Utility callbacks only publish requests. */
static void theme_run_pending_toggle(void)
{
    /* An armed start becomes an ordinary toggle request rather than a second
       way of switching. The tab artwork, the image table and the waveform
       palette then move together, through the one path that already does it. */
    if (theme_light_armed && !theme_light_active() &&
        monotonic_enough_us() >= theme_start_light_not_before_us) {
        theme_light_armed = 0;
        __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 1);
        log_line("display mode: the player has painted, taking the display light");
    }
    int request = __atomic_load_n(&theme_toggle_pending, __ATOMIC_SEQ_CST);
    if ((request == 1 || request == 2) &&
        __sync_bool_compare_and_swap(&theme_toggle_pending, request, 3)) {
        int light = !theme_light_active();
        framework->images->select_variant(light);
        theme_waveform_apply(light);
        if (request == 2) {
            theme_refresh_pending = 0;
            if (((int (*)(void))0x001126d0)() == 7)
                ((int (*)(int))0x0010167c)(1);
        } else {
            theme_refresh_pending = 1u;
        }
        __atomic_store_n(&theme_toggle_pending, 0, __ATOMIC_SEQ_CST);
    }
    if (theme_refresh_pending) {
        theme_refresh_pending = 0;
        ((void (*)(void))0x0018e214)();
        framework->panels->refresh();
        ((void (*)(void))0x00101aac)();
    }
}

/* These are the native list iterator slots, not resource object IDs. */
#define THEME_LIST_FIRST_SLOT 20u
#define THEME_LIST_NEXT_SLOT 18u
#define THEME_CONTROL_CHILDREN_SLOT 17u
#define THEME_CHILD_REFRESH_LIMIT 64u

static unsigned int theme_queue_children(void *children)
{
    if (!children)
        return 0;
    void **vtable = *(void ***)children;
    void *child = ((void *(*)(void *))vtable[THEME_LIST_FIRST_SLOT])(children);
    void *manager = ((void *(*)(void))GET_HMI_MANAGER)();
    unsigned int count = 0;
    while (child && count < THEME_CHILD_REFRESH_LIMIT) {
        ((void (*)(void *, int, void *))REFRESH_GLYPH)(manager, -1, child);
        count++;
        child = ((void *(*)(void *))vtable[THEME_LIST_NEXT_SLOT])(children);
    }
    return count;
}

static unsigned int theme_refresh_header(void)
{
    void *header = *(void **)THEME_HEADER_CONTROL;
    if (!header || ((const uint8_t *)header)[4] != 0x17u)
        return 0;
    /* The header has visible groups beneath a hidden control. Root traversal
       skips them. Queue the actual children without changing visibility. */
    void **vtable = *(void ***)header;
    return theme_queue_children(
        ((void *(*)(void *))vtable[THEME_CONTROL_CHILDREN_SLOT])(header));
}

static void hooked_theme_render_pass(void *manager)
{
    if (theme_render_active) { original_theme_render_pass(manager); return; }
    theme_render_active = 1;
    int previous_theme = theme_light_active();
    theme_run_pending_toggle();
    int repaint = theme_run_conversions() || previous_theme != theme_light_active();
    if (repaint) ((int (*)(void))THEME_DIRTY_WINDOWS)();
    original_theme_render_pass(manager);
    /* A winscape entry consumes the root queue. Draw the independent header
       groups afterwards, in a second native pass on the same UI thread. */
    if (repaint && theme_refresh_header())
        original_theme_render_pass(manager);
    theme_render_active = 0;
}

#include "rx3_theme_conversion.h"

/* The pane's palette as the firmware ships it. Two entries hold whichever mode
 * is current, so both values are accepted for those and exactly one for the
 * rest: this is the whole check that the table under the address is the table
 * meant, and it is the reason a wrong address writes nothing.
 */
static int theme_wave_table_is_known(const volatile uint16_t *table)
{
    static const uint16_t fixed[THEME_WAVE_TABLE_WORDS] = {
        0x0000u, 0xffffu, 0xfd20u, 0u, 0xff9au, 0xd6ffu, 0u, 0xf75au
    };
    for (unsigned int index = 0; index < THEME_WAVE_TABLE_WORDS; index++) {
        uint16_t found = table[index];
        if (index == THEME_WAVE_INSET_INDEX) {
            if (found != THEME_WAVE_INSET_DARK && found != THEME_WAVE_INSET_LIGHT)
                return 0;
        } else if (index == THEME_WAVE_TINT_INDEX) {
            if (found != THEME_WAVE_TINT_DARK && found != THEME_WAVE_TINT_LIGHT)
                return 0;
        } else if (found != fixed[index]) {
            return 0;
        }
    }
    return 1;
}

/* One firmware word through the core's guarded writer: it is written only
 * while it still holds what was just checked, and the previous bytes survive
 * a failure. Leaving a pane dark is the fallback, never a half-written table.
 */
static int theme_write_word(unsigned long address, const void *expected,
                            const void *wanted, unsigned int length)
{
    if (!memcmp((const void *)address, wanted, length)) return 1;
    return framework->write_guarded &&
           framework->write_guarded(address, expected, wanted, length);
}

/* Put the waveform pane into the mode the rest of the interface is in.
 *
 * The pane keeps a dark ground either way. What changes is how far it is inset
 * and the tint of its own furniture, so that it reads as a well set into a
 * light room rather than as a hole punched in it.
 */
static void theme_waveform_apply(int light)
{
    const volatile uint16_t *table = (const volatile uint16_t *)THEME_WAVE_TABLE;
    if (!theme_wave_table_is_known(table)) {
        log_line("light theme: the waveform palette is not the one expected, "
                 "the pane is left alone");
        return;
    }
    uint32_t opcode = *(const volatile uint32_t *)THEME_WAVE_INSTRUCTION;
    if (opcode != THEME_WAVE_OPCODE_DARK && opcode != THEME_WAVE_OPCODE_LIGHT) {
        log_line("light theme: the waveform inset is not where it was, "
                 "the pane is left alone");
        return;
    }
    uint16_t inset = table[THEME_WAVE_INSET_INDEX], tint = table[THEME_WAVE_TINT_INDEX];
    uint16_t wanted_inset = light ? THEME_WAVE_INSET_LIGHT : THEME_WAVE_INSET_DARK;
    uint16_t wanted_tint = light ? THEME_WAVE_TINT_LIGHT : THEME_WAVE_TINT_DARK;
    uint32_t wanted_opcode = light ? THEME_WAVE_OPCODE_LIGHT : THEME_WAVE_OPCODE_DARK;
    if (!theme_write_word(THEME_WAVE_TABLE + THEME_WAVE_INSET_INDEX * 2u,
                          &inset, &wanted_inset, 2u) ||
        !theme_write_word(THEME_WAVE_TABLE + THEME_WAVE_TINT_INDEX * 2u,
                          &tint, &wanted_tint, 2u))
        return;
    if (!theme_write_word(THEME_WAVE_INSTRUCTION, &opcode, &wanted_opcode, 4u))
        return;
    /* Both decks, so the change lands without waiting for a track to load. */
    ((void (*)(unsigned int, unsigned int))REFRESH_DECK)(0u, 1u);
    ((void (*)(unsigned int, unsigned int))REFRESH_DECK)(1u, 1u);
}

/* The one letter the module exports chooses the starting mode. The four are
   distinct states rather than one switch: what the deck shows at the first
   frame, and whether it moves afterwards, are separate questions. l starts
   light, d runs the global dark remap, w is light once the player has painted,
   and anything else is dark and switchable from Utility. */
static void theme_read_mode(const char *theme)
{
    theme_global_dark = theme[0] == 'd';
    theme_light_armed = theme[0] == 'w';
    if (theme_global_dark) {
        log_line("global dark theme active (sentinel: " THEME_DARK_SENTINEL ")");
    } else if (theme_light_armed) {
        theme_start_light_not_before_us = monotonic_enough_us() + 1000000u;
        log_line("display mode: light, held back until the player has painted once");
    } else if (theme[0] == 'l') {
        log_line("display mode: light from the first frame");
    } else {
        log_line("display mode: dark to begin with, switch it in Utility");
    }
}

static const struct rx3_image_policy theme_policy = {theme_remap_image, theme_fill};

static int theme_feature_install(void)
{
    if (!theme_enabled)
        return 0;
    if (memcmp((const void *)THEME_DIRTY_WINDOWS, theme_dirty_windows_guard, 8)) {
        log_line("light theme: unexpected window invalidation prologue");
        return 0;
    }
    original_theme_render_pass = (void (*)(void *))install_hook(
        &theme_render_pass_hook, THEME_RENDER_PASS, theme_render_pass_guard,
        hooked_theme_render_pass);
    if (!original_theme_render_pass)
        return 0;
    theme_render_pass_installed = 1;
    if (!framework->images->claim_variants(&theme_enabled, &theme_policy))
        return 0;
    /* The fill substitution is the theme; the key only turns it on. So a key
       that cannot be watched leaves a working feature with no switch, which is
       worth saying and is not worth refusing the feature over. */
    theme_key_registered = framework->input->register_key(&theme_enabled, 20u, theme_key);
    if (!theme_key_registered)
        log_line("light theme: no live switch, SHIFT+SHORTCUT will not toggle it");
    utility_install_theme_row();
    framework->images->select_variant(0);
    log_line("light theme: solid fills are ready to be replaced");
    return 1;
}

static void theme_feature_remove(void)
{
    if (theme_render_pass_installed && uninstall_hook(&theme_render_pass_hook)) {
        theme_render_pass_installed = 0;
        original_theme_render_pass = 0;
    }
    utility_remove_theme_row();
    theme_refresh_pending = 0;
    int was_light = theme_light_active();
    framework->images->release_variants(&theme_enabled);
    if (was_light)
        theme_waveform_apply(0);
    framework->input->unregister_owner(&theme_enabled);
    theme_key_registered = 0;
    theme_toggle_pending = 0;
}

#endif /* RX3_THEME_FEATURE_H */
