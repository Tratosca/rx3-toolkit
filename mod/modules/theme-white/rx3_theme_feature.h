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
static struct installed_hook theme_browse_rect_hook;
static void (*original_theme_browse_rect)(void *render, void *rect);
static int theme_browse_rect_installed;
static unsigned char theme_browse_row_blue[12];
static unsigned char theme_browse_right_row_blue[12];
static unsigned int theme_browse_track_active;
static unsigned int theme_browse_list_start = 379u;
static unsigned int theme_browse_list_split = 857u;
static unsigned char theme_source_row_blue[2];
/* Utility paints exactly one blue cell: the chosen row's name, or its value
   while the value is being changed. 0 until a cell has been seen. */
static unsigned int theme_utility_blue_cell;
static unsigned int theme_utility_name_refresh_pending;
static const uint8_t theme_browse_rect_guard[8] = {
    0xb0, 0x31, 0xd1, 0xe1, 0xf0, 0x4f, 0x2d, 0xe9
};
static int theme_key_registered;

/* Converted pixels live in one arena the module allocates once and keeps for
 * the life of the process: published records keep pointing into it.
 */
static uint8_t *theme_arena;
static size_t theme_arena_used;
static unsigned long theme_memory_kb;
static int theme_run_conversions(void);
static int theme_requests_pending(void);
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
#include "rx3_theme_text.h"

static unsigned int theme_text_remap(const struct rx3_text_draw *draw)
{
    unsigned int view = (unsigned int)((int (*)(void))0x001126d0u)();
    unsigned int selected_background = 0u;
    if (view == 3u && draw->box[0] >= 108u && draw->box[0] < 1280u &&
        draw->box[1] >= 60u &&
        draw->box[1] < 60u + 12u * 50u) {
        unsigned int row = (draw->box[1] - 60u) / 50u;
        selected_background = draw->box[0] < 108u ?
            ((draw->list_flags & 0x10u) && draw->selection_index == row) :
            draw->box[0] < theme_browse_list_start ? 0u :
            draw->box[0] < theme_browse_list_split ?
            (theme_browse_track_active && theme_browse_row_blue[row]) :
            (theme_browse_track_active && theme_browse_right_row_blue[row]);
    }
    if (view == 12u && draw->box[0] >= 100u && draw->box[0] < 735u &&
        draw->box[1] >= 100u && draw->box[1] < 282u) {
        unsigned int row = draw->box[1] < 190u ? 0u : 1u;
        selected_background = theme_source_row_blue[row];
    }
    if (view == 7u && draw->box[1] >= 11u && draw->box[1] < 11u + 12u * 52u) {
        unsigned int row = (draw->box[1] - 11u) / 52u;
        unsigned int side = draw->box[0] < 734u ? 1u : 2u;
        /* The cell can lag the cursor within one pass: rows drawn before the
           new blue rectangle would still see the old one. Trust it only on
           the cursor's row; elsewhere the name under the cursor is the cell. */
        unsigned int cell = theme_utility_blue_cell;
        selected_background = cell && (cell >> 2) == draw->selection_index ?
            cell == ((row << 2) | side) :
            side == 1u && draw->selection_index == row;
    }
    return theme_text_colour(theme_light_active(),
                             theme_text_light_surface(view, draw->layer, draw->box[1]),
                             draw->native_colour, selected_background);
}
static const struct rx3_text_policy theme_text_policy = {theme_text_remap};

/* Native list and SOURCE row rectangles carry the live selection colour,
   even when their text models do not change with focus. */
static void theme_browse_rect(void *render, void *rect)
{
    unsigned int view = (unsigned int)((int (*)(void))0x001126d0u)();
    if (rect && (view == 3u || view == 7u || view == 12u)) {
        const uint8_t *model = rect;
        uint16_t layer, box[4];
        uint32_t colour;
        memcpy(&layer, model + 0x10u, sizeof(layer));
        memcpy(box, model + 0x18u, sizeof(box));
        memcpy(&colour, model + 0x28u, sizeof(colour));
        if (view == 7u && layer == 0x0001u && colour == 0xff1c1f00u &&
            box[1] < 12u * 52u &&
            ((box[0] == 8u && box[2] == 734u) || (box[0] == 735u && box[2] == 1280u))) {
            unsigned int cell = (((box[1] + 10u) / 52u) << 2) |
                                (box[0] == 8u ? 1u : 2u);
            if (cell != theme_utility_blue_cell) {
                theme_utility_name_refresh_pending =
                    theme_utility_name_row(theme_utility_blue_cell, cell);
                theme_utility_blue_cell = cell;
            }
        }
        if (view == 3u && layer == 0x0801u && box[0] == 0u &&
            box[1] == 50u && box[2] == 1280u && box[3] == 659u) {
            theme_browse_track_active = 0u;
            theme_browse_list_start = 379u;
            theme_browse_list_split = 857u;
            memset(theme_browse_row_blue, 0, sizeof(theme_browse_row_blue));
            memset(theme_browse_right_row_blue, 0,
                   sizeof(theme_browse_right_row_blue));
        }
        if (view == 3u && layer == 0x0801u &&
            box[1] >= 50u && box[1] < 50u + 12u * 50u &&
            box[3] == box[1] + 53u && (box[1] - 50u) % 50u == 0u) {
            unsigned int row = (box[1] - 50u) / 50u;
            if ((box[0] == 379u || box[0] == 108u) &&
                box[2] == 857u) {
                theme_browse_track_active = 1u;
                theme_browse_list_start = box[0];
                theme_browse_list_split = box[0] == 108u ? 735u : 857u;
                theme_browse_row_blue[row] = colour == 0xff1c1f00u;
            } else if (box[0] == 857u && box[2] == 1280u) {
                theme_browse_track_active = 1u;
                theme_browse_right_row_blue[row] = colour == 0xff1c1f00u;
            }
        }
        if (view == 12u && layer == 0x0101u && box[0] == 0u &&
            box[2] == 735u && box[3] == box[1] + 90u &&
            (box[1] == 100u || box[1] == 192u)) {
            unsigned int row = box[1] == 100u ? 0u : 1u;
            theme_source_row_blue[row] = colour == 0xff1c1f00u;
        }
    }
    original_theme_browse_rect(render, rect);
}

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
static uint64_t theme_arena_wait_deadline_us;
static unsigned int theme_refresh_pending;
static unsigned int theme_home_repaint_pending;
static int theme_last_text_view = -1;
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

/* Make each deck strip repaint its message and backing in the new mode: the
   next native counter update sees a caution ID it has not drawn. */
static void theme_forget_counter_cautions(void)
{
    if (memcmp((const void *)THEME_COUNTER_CAUTION_CACHE,
               theme_counter_caution_cache_guard, 8))
        return;
    volatile uint32_t *ids = (volatile uint32_t *)THEME_COUNTER_CAUTION_IDS;
    ids[0] = 0xffffffffu;
    ids[1] = 0xffffffffu;
}

/* Called at the render-pass boundary, before the native queue is consumed.
   Changing the table from a per-glyph callback mixes two themes in one pass.
   The key and Utility callbacks only publish requests. */
/* The margins beside and under the deck strips (x 0-9, 630-649, 1270-1279
   at y 709-788) belong to tall narrow HOME windows that the screen reload
   recreates on reused surfaces. The player repaints their top part only, so
   the bottom keeps the previous mode's pixels. Fill that part with the stock
   black; the fill adapter turns it into the light panel colour in LIGHT. */
static unsigned int theme_margin_repaint_passes;

static void theme_repaint_margins(void)
{
    if (memcmp((const void *)THEME_HW_FILL_RECT, theme_hw_fill_rect_guard, 8) ||
        *(const volatile uint32_t *)THEME_LAYER0_LITERAL != THEME_LAYER0) return;
    unsigned long window = *(volatile uint32_t *)(THEME_LAYER0 + THEME_LAYER_WINDOWS);
    for (unsigned int n = 0; window && n < THEME_WINDOW_WALK_LIMIT; n++) {
        int y = *(volatile int *)(window + THEME_WINDOW_Y);
        unsigned int width = *(volatile uint16_t *)(window + THEME_WINDOW_WIDTH);
        unsigned int height = *(volatile uint16_t *)(window + THEME_WINDOW_HEIGHT);
        /* The left and middle margins end at y 789, the right one at 790. */
        if (width && width <= THEME_MARGIN_MAX_WIDTH && y < THEME_MARGIN_TOP &&
            y + (int)height >= THEME_MARGIN_BOTTOM) {
            volatile uint32_t *colour = (volatile uint32_t *)(window + THEME_WINDOW_COLOUR);
            uint32_t saved = *colour;
            *colour = 0u;
            ((int (*)(unsigned long, int, int, unsigned int))THEME_HW_FILL_RECT)(
                window, 0, THEME_MARGIN_TOP - y,
                width | ((unsigned int)(THEME_MARGIN_BOTTOM - THEME_MARGIN_TOP) << 16));
            *colour = saved;
        }
        window = *(volatile uint32_t *)(window + THEME_WINDOW_NEXT);
    }
}

/* A few passes after a switch on HOME, once the reload has drawn and the
   windows are the new ones. */
static void theme_run_margin_repaint(void)
{
    if (!theme_margin_repaint_passes || --theme_margin_repaint_passes ||
        ((int (*)(void))0x001126d0u)() != 1)
        return;
    /* Keyed windows show the screen surface where they are transparent,
       such as the bottom row: clear it in the new mode first. */
    if (!memcmp((const void *)THEME_CLEAR_SCREEN, theme_clear_screen_guard, 8))
        ((int (*)(void))THEME_CLEAR_SCREEN)();
    theme_repaint_margins();
    ((int (*)(void))THEME_DIRTY_WINDOWS)();
}

static void theme_run_pending_toggle(void)
{
    /* An armed start becomes an ordinary toggle request rather than a second
       way of switching. The tab artwork, the image table and the waveform
       palette then move together, through the one path that already does it. */
    int starting_light = 0;
    if (theme_light_armed && !theme_light_active() &&
        monotonic_enough_us() >= theme_start_light_not_before_us) {
        theme_light_armed = 0;
        starting_light = 1;
        __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 1);
        log_line("display mode: the player has painted, taking the display light");
    }
    int request = __atomic_load_n(&theme_toggle_pending, __ATOMIC_SEQ_CST);
    if ((request == 1 || request == 2) && !starting_light &&
        !theme_light_active() && !theme_global_dark && theme_requests_pending()) {
        uint64_t now = monotonic_enough_us();
        if (!theme_arena_wait_deadline_us)
            theme_arena_wait_deadline_us = now + 1000000u;
        /* The watcher allocates after the firmware publishes its image table.
           Give it a bounded chance before falling back to the stock pixels. */
        if (!__atomic_load_n(&theme_arena, __ATOMIC_SEQ_CST) &&
            now < theme_arena_wait_deadline_us)
            return;
    }
    /* During DARK, images drawn on the current screen are converted into the
       dormant LIGHT table. If a DJ switches before that work is complete,
       finish it under the still-dark screen before exposing the light one. */
    if ((request == 1 || request == 2) && !starting_light &&
        !theme_light_active() && !theme_global_dark &&
        __atomic_load_n(&theme_arena, __ATOMIC_SEQ_CST) &&
        __atomic_load_n(&theme_memory_kb, __ATOMIC_SEQ_CST) >= THEME_CONVERT_RESERVE_KB &&
        theme_requests_pending())
        return;
    theme_arena_wait_deadline_us = 0;
    if ((request == 1 || request == 2) &&
        __sync_bool_compare_and_swap(&theme_toggle_pending, request, 3)) {
        /* A request taken while the start is still armed came from the DJ
           (SHIFT + SHORTCUT or Utility): the armed start clears itself before
           it publishes. Their choice wins, or the next switch to dark would
           find the start still armed and go light again on its own. */
        theme_light_armed = 0;
        int light = !theme_light_active();
        framework->images->select_variant(light);
        framework->text->invalidate();
        theme_forget_counter_cautions();
        /* The main screen's ground is painted when the screen is entered and
           never again. Enter it once more, as leaving SHORTCUT does, so the
           ground and the waveform pane edge follow the new mode. */
        if (((int (*)(void))0x001126d0u)() == 1 &&
            !memcmp((const void *)THEME_SHOW_SCREEN, theme_show_screen_guard, 8)) {
            if (!memcmp((const void *)THEME_SIMPLE_COUNTER_CLEAR,
                        theme_simple_counter_clear_guard, 8))
                ((void (*)(void))THEME_SIMPLE_COUNTER_CLEAR)();
            theme_margin_repaint_passes = THEME_MARGIN_REPAINT_PASSES;
            ((int (*)(unsigned int))THEME_SHOW_SCREEN)(0u);
        }
        theme_waveform_apply(light);
        theme_home_repaint_pending = light != 0;
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

static unsigned int theme_refresh_home_child(unsigned int target)
{
    if (((int (*)(void))0x001126d0u)() != 1) return 0;
    void *component = ((void *(*)(void))THEME_COMPONENT_MANAGER)();
    void *winscape = component ?
        ((void *(*)(void *))THEME_ACTIVE_WINSCAPE)(component) : 0;
    if (!winscape) return 0;
    void *children = (uint8_t *)winscape + 0x24u;
    void **vtable = *(void ***)children;
    void *child = ((void *(*)(void *))vtable[THEME_LIST_FIRST_SLOT])(children);
    for (unsigned int i = 0; child && i < 3u; i++) {
        if (i == target) {
            void *manager = ((void *(*)(void))GET_HMI_MANAGER)();
            ((void (*)(void *, int, void *))REFRESH_GLYPH)(manager, -1, child);
            return 1;
        }
        child = ((void *(*)(void *))vtable[THEME_LIST_NEXT_SLOT])(children);
    }
    return 0;
}

static void theme_refresh_text_for_view(void)
{
    int view = ((int (*)(void))0x001126d0u)();
    if (view != 7) {
        theme_utility_blue_cell = 0;
        theme_utility_name_refresh_pending = 0;
    }
    if (theme_light_active() && view != theme_last_text_view &&
        (view == 3 || view == 7 || view == 12))
        framework->text->invalidate();
    theme_last_text_view = view;
}

static unsigned int theme_browse_refresh_due;
static void theme_refresh_utility_name(void *manager)
{
    unsigned int pending = theme_utility_name_refresh_pending;
    theme_utility_name_refresh_pending = 0;
    if (!pending || pending > 12u || !theme_light_active() ||
        ((int (*)(void))0x001126d0u)() != 7 ||
        memcmp((const void *)THEME_REFRESH_OBJECT, theme_refresh_object_guard, 8) ||
        memcmp((const void *)THEME_UTILITY_NAME_IDS, theme_utility_name_ids_guard, 8) ||
        memcmp((const void *)THEME_UTILITY_ROOT_LITERAL, theme_utility_root_literal_guard, 8))
        return;
    const uint16_t *names = (const uint16_t *)THEME_UTILITY_NAME_IDS;
    void *root = *(void **)THEME_UTILITY_ROOT_PTR;
    if (!root) return;
    ((void (*)(void *, unsigned int))THEME_REFRESH_OBJECT)(root, names[pending - 1u]);
    original_theme_render_pass(manager);
}
static void hooked_theme_render_pass(void *manager)
{
    if (theme_render_active) { original_theme_render_pass(manager); return; }
    theme_render_active = 1;
    int previous_theme = theme_light_active();
    theme_run_pending_toggle();
    theme_run_margin_repaint();
    theme_refresh_text_for_view();
    int converted = theme_run_conversions();
    /* A DARK prewarm publishes only into the dormant LIGHT table. It changes
       no visible pixel, so it must not dirty every native window. */
    int repaint = (converted && (theme_light_active() || theme_global_dark)) ||
                  previous_theme != theme_light_active();
    /* Rail tiles drawn before their conversion was published keep the stock
       pixels: the dirty-window pass does not reach them. Once nothing is left
       to convert, ask BROWSE for one native refresh. */
    if (converted && theme_light_active() &&
        ((int (*)(void))0x001126d0u)() == 3) theme_browse_refresh_due = 1u;
    if (theme_browse_refresh_due && !theme_requests_pending()) {
        theme_browse_refresh_due = 0u;
        theme_refresh_pending = 1u;
    }
    if (repaint) ((int (*)(void))THEME_DIRTY_WINDOWS)();
    original_theme_render_pass(manager);
    /* A winscape entry consumes the root queue. Draw the independent header
       groups afterwards, in a second native pass on the same UI thread. */
    if (theme_light_active() &&
        ((int (*)(void))0x001126d0u)() == 1 &&
        (theme_home_repaint_pending || repaint)) {
        theme_home_repaint_pending = 0;
        if (theme_refresh_home_child(1u))
            original_theme_render_pass(manager);
        unsigned int queued = theme_refresh_header();
        queued += theme_refresh_home_child(2u);
        if (queued) original_theme_render_pass(manager);
    } else if (repaint && theme_refresh_header()) {
        original_theme_render_pass(manager);
    }
    theme_refresh_utility_name(manager);
    theme_render_active = 0;
}

#include "rx3_theme_conversion.h"
static int theme_requests_pending(void)
{
    if (theme_job.source) return 1;
    for (unsigned int i = 0; i < sizeof(theme_requested); i++)
        if (theme_requested[i]) return 1;
    return 0;
}

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
    /* l and w take the same armed toggle at a render boundary; only w waits
       for the player's first paint. l used to log and never switch. */
    theme_light_armed = theme[0] == 'w' || theme[0] == 'l';
    if (theme_global_dark) {
        log_line("global dark theme active (sentinel: " THEME_DARK_SENTINEL ")");
    } else if (theme[0] == 'w') {
        theme_start_light_not_before_us = monotonic_enough_us() + 1000000u;
        log_line("display mode: light, held back until the player has painted once");
    } else if (theme[0] == 'l') {
        theme_start_light_not_before_us = 0u;
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
    if (memcmp((const void *)THEME_DIRTY_WINDOWS, theme_dirty_windows_guard, 8) ||
        memcmp((const void *)THEME_COMPONENT_MANAGER, theme_component_manager_guard, 8) ||
        memcmp((const void *)THEME_ACTIVE_WINSCAPE, theme_active_winscape_guard, 8)) {
        log_line("light theme: unexpected window invalidation prologue");
        return 0;
    }
    original_theme_render_pass = (void (*)(void *))install_hook(
        &theme_render_pass_hook, THEME_RENDER_PASS, theme_render_pass_guard,
        hooked_theme_render_pass, (void **)&original_theme_render_pass);
    if (!original_theme_render_pass)
        return 0;
    theme_render_pass_installed = 1;
    original_theme_browse_rect = (void (*)(void *, void *))install_hook(
        &theme_browse_rect_hook, 0x001d2decu, theme_browse_rect_guard,
        (void *)theme_browse_rect, (void **)&original_theme_browse_rect);
    if (!original_theme_browse_rect)
        return 0;
    theme_browse_rect_installed = 1;
    if (!framework->images->claim_variants(&theme_enabled, &theme_policy))
        return 0;
    if (!framework->text || !framework->text->claim(&theme_enabled, &theme_text_policy))
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
    if (theme_browse_rect_installed && uninstall_hook(&theme_browse_rect_hook)) {
        theme_browse_rect_installed = 0;
        original_theme_browse_rect = 0;
    }
    if (theme_render_pass_installed && uninstall_hook(&theme_render_pass_hook)) {
        theme_render_pass_installed = 0;
        original_theme_render_pass = 0;
    }
    utility_remove_theme_row();
    theme_refresh_pending = 0;
    theme_home_repaint_pending = 0;
    int was_light = theme_light_active();
    framework->images->release_variants(&theme_enabled);
    if (framework->text) framework->text->release(&theme_enabled);
    if (was_light)
        theme_waveform_apply(0);
    framework->input->unregister_owner(&theme_enabled);
    theme_key_registered = 0;
    theme_toggle_pending = 0;
    theme_arena_wait_deadline_us = 0;
}

#endif /* RX3_THEME_FEATURE_H */
