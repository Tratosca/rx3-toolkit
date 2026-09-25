/* SPDX-License-Identifier: MPL-2.0
 * Light theme implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_THEME_FEATURE_H
#define RX3_THEME_FEATURE_H

static int theme_enabled;
static struct installed_hook theme_render_pass_hook;
static void (*original_theme_render_pass)(void *manager);

/* The two image tables, and the store the light one points into.
 *
 * Two tables rather than one converted in place: switching back to dark is a
 * single pointer store, and the stock pixels are never touched, so nothing has
 * to be converted twice or converted back.
 */
static uint8_t *theme_dark_table;
static uint8_t *theme_light_table;
static uint8_t *theme_arena;
static size_t theme_arena_used;
static int theme_arena_reported;
static int theme_conversion_enabled;
static uint8_t theme_id_done[(STOCK_IMAGE_COUNT + 7u) / 8u];
static const uint16_t *theme_seen_source[4096];
static uint32_t theme_seen_offset[4096];
static unsigned int theme_seen_count;


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

static void hooked_hw_fill_rect(void *target, const uint8_t *rect)
{
    if (theme_light_active && rect && !theme_suspend_fill) {
        volatile unsigned int *fill = (volatile unsigned int *)THEME_FILL_REGISTER;
        if (theme_fill_is_chrome(*fill)) {
            uint16_t width;
            uint16_t height;
            memcpy(&width, rect + THEME_RECT_WIDTH_OFFSET, sizeof(width));
            memcpy(&height, rect + THEME_RECT_HEIGHT_OFFSET, sizeof(height));
            *fill = theme_fill_for_rect(width, height);
        }
    }
    original_hw_fill_rect(target, rect);
}

/* Whether SHIFT is down, one flag per channel. */
static uint8_t theme_shift_held[THEME_KEY_CHANNELS];
/* Set when a SHORTCUT press was taken for the combination, so its release is
   taken too. Without it the player sees a key come up that never went down. */
static uint8_t theme_shortcut_swallowed;

static int theme_shift_is_held(void)
{
    for (unsigned int channel = 0; channel < THEME_KEY_CHANNELS; channel++)
        if (theme_shift_held[channel])
            return 1;
    return 0;
}
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
static void theme_light_tab_assets(void);
#include "rx3_theme_utility.h"

static void theme_waveform_apply(int light);

/* Watch for SHIFT + SHORTCUT and swallow the SHORTCUT that completes it.
 *
 * Swallowing matters. SHORTCUT on its own is a stock function, and letting it
 * through as well would mean the display mode and whatever that function does
 * both happen on one press. The release is swallowed too, or the player is left
 * believing a key it never saw pressed has just come up.
 */
/* How many key events are described before the log goes quiet.
 *
 * This runs on the input path, so an unbounded line here writes to the drive on
 * every press. Twelve is enough to see a modifier go down, a key follow it and
 * both come up, which is the whole question.
 */
#define THEME_KEY_TRACE_LIMIT 12u
static unsigned int theme_key_traced;

/* One line per event, key, operation and channel packed into it.
 *
 * Four lines an event filled a small budget with whatever the deck was already
 * emitting, before the operator had touched anything. One line goes further on
 * the same number of writes, and this runs on the input path where each write
 * reaches a log on the drive.
 */
static void theme_trace_key(unsigned int key, unsigned int operation,
                            unsigned int channel)
{
    if (!render_probe_enabled || theme_key_traced >= THEME_KEY_TRACE_LIMIT)
        return;
    theme_key_traced++;
    log_number("key kkkkooocc =",
               (key & 0xffffu) * 100000u + (operation & 0xffu) * 100u +
               (channel & 0xffu));
}

static int hooked_send_key(void *target, unsigned int key, unsigned int operation,
                           unsigned int channel, unsigned int a, unsigned int b,
                           unsigned int c)
{
    theme_trace_key(key, operation, channel);
    unsigned int slot = channel < THEME_KEY_CHANNELS ? channel : 0u;
    if (key == THEME_KEY_SHIFT) {
        if (operation == THEME_KEY_PRESS) {
            theme_shift_held[slot] = 1u;
            samples_shift_pressed();
        } else if ((operation & ~1u) == THEME_KEY_RELEASE)
            theme_shift_held[slot] = 0u;
    } else if (theme_enabled && key == THEME_KEY_SHORTCUT) {
        /* SHIFT is reported per deck, on channels 1 and 2. SHORTCUT belongs to
           the unit and arrives on channel 0, so its own channel never holds the
           modifier. Either deck's SHIFT completes the combination, which is
           also what the hand does: one is pressed on whichever side is free. */
        if (operation == THEME_KEY_PRESS && theme_shift_is_held()) {
            theme_shortcut_swallowed = 1u;
            __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 1);
            return 0;
        }
        if ((operation & ~1u) == THEME_KEY_RELEASE && theme_shortcut_swallowed) {
            theme_shortcut_swallowed = 0u;
            return 0;
        }
    }
    return original_send_key(target, key, operation, channel, a, b, c);
}

/* Called at the render-pass boundary, before the native queue is consumed.
   Changing the table from a per-glyph callback mixes two themes in one pass.
   The key and Utility callbacks only publish requests. */
static void theme_run_pending_toggle(void)
{
    /* An armed start becomes an ordinary toggle request rather than a second
       way of switching. The tab artwork, the image table and the waveform
       palette then move together, through the one path that already does it. */
    if (theme_light_armed && !theme_light_active &&
        monotonic_enough_us() >= theme_start_light_not_before_us) {
        theme_light_armed = 0;
        __sync_bool_compare_and_swap(&theme_toggle_pending, 0, 1);
        log_line("display mode: the player has painted, taking the display light");
    }
    int request = __atomic_load_n(&theme_toggle_pending, __ATOMIC_SEQ_CST);
    if ((request == 1 || request == 2) &&
        __sync_bool_compare_and_swap(&theme_toggle_pending, request, 3)) {
        theme_light_active = !theme_light_active;
        theme_light_tab_assets();
        uint8_t *table = theme_light_active && theme_light_table
            ? theme_light_table : theme_dark_table;
        if (table) {
            __sync_synchronize();
            *(uint8_t **)IMAGE_TABLE_POINTER = table;
        }
        theme_waveform_apply(theme_light_active);
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
        refresh_performance_ui();
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
    int previous_theme = theme_light_active;
    theme_run_pending_toggle();
    if (previous_theme != theme_light_active)
        ((int (*)(void))THEME_DIRTY_WINDOWS)();
    original_theme_render_pass(manager);
    /* A winscape entry consumes the root queue. Draw the independent header
       groups afterwards, in a second native pass on the same UI thread. */
    if (previous_theme != theme_light_active && theme_refresh_header())
        original_theme_render_pass(manager);
}

/* Optional light artwork falls back to the original dark tabs. Generic image
   conversion cannot preserve the contrast of their selected-state labels. */
static void theme_light_tab_assets(void)
{
    if (!theme_light_table)
        return;
    for (unsigned int i = 0; i < TAB_IMAGE_COUNT; i++) {
        uint8_t *record = theme_light_table + (TAB_IMAGE_KEY + i) * 44u;
        uint16_t width = 180u, height = 50u;
        const void *source = light_tab_assets_ready
            ? light_tab_image_pixels[i] : tab_image_pixels[i];
        uint32_t pixels = (uint32_t)(unsigned long)source -
                          (uint32_t)(unsigned long)theme_light_table;
        uint32_t palette = 0;
        memcpy(record + 4u, &width, 2u);
        memcpy(record + 6u, &height, 2u);
        record[0x18u] = 2u;
        record[0x19u] = 0u;
        memcpy(record + 0x20u, &pixels, 4u);
        memcpy(record + 0x24u, &palette, 4u);
    }

    /* The pad row's glyphs, the same way: the light artwork keeps the dark
       set's image IDs and only this table points at it, so the row never has to
       choose an atlas. Whichever table the toggle installed decides, which is
       what keeps the lettering in step with the chrome around it. */
    if (pad_atlas_ready && pad_atlas_light_blob)
        pad_atlas_install_records(theme_light_table, pad_atlas_light_blob);
}

/* A source bitmap shared by several records is converted once. The source
   address is the cache key used by the released renderer. */
static void theme_remap_image(unsigned int image)
{
    if (!theme_conversion_enabled ||
        (!theme_light_active && !theme_global_dark) || !theme_light_table ||
        !theme_dark_table || image >= STOCK_IMAGE_COUNT ||
        (image == LOGO_IMAGE_INDEX && main_logo_ready)) return;
    unsigned int bit = 1u << (image & 7u);
    if (theme_id_done[image >> 3u] & bit) return;
    theme_id_done[image >> 3u] |= bit;
    const uint8_t *record = theme_dark_table + image * 44u;
    uint16_t width, height;
    uint32_t offset;
    memcpy(&width, record + 4u, 2u);
    memcpy(&height, record + 6u, 2u);
    memcpy(&offset, record + 0x20u, 4u);
    if ((record[0x18u] != 1u && record[0x18u] != 2u) || record[0x19u] ||
        !width || !height) return;
    uint64_t bytes = (uint64_t)width * height * 2u;
    if (bytes > THEME_IMAGE_MAX_BYTES) return;
    const uint16_t *source = (const uint16_t *)(theme_dark_table + offset);
    uint32_t from_stock = (uint32_t)(unsigned long)source -
                          (uint32_t)(unsigned long)theme_stock_table;
    if (theme_stock_table && from_stock <= STOCK_IMAGE_COUNT * 44u + 43u) return;
    if (!theme_arena) {
        if (memory_available_kb() < THEME_ARENA_FLOOR_KB) {
            theme_conversion_enabled = 0;
            log_line("light theme: image conversion disabled, memory reserve too low");
            return;
        }
        theme_arena = mmap(0, THEME_ARENA_BYTES, PROT_READ | PROT_WRITE,
                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        if (theme_arena == MAP_FAILED) {
            theme_arena = 0;
            theme_conversion_enabled = 0;
            return;
        }
    }
    if (memory_available_kb() < THEME_CONVERT_RESERVE_KB) return;
    uint32_t moved = 0u;
    for (unsigned int i = 0; i < theme_seen_count; i++)
        if (theme_seen_source[i] == source) { moved = theme_seen_offset[i]; break; }
    if (!moved) {
        if (bytes > THEME_ARENA_BYTES - theme_arena_used) {
            if (!theme_arena_reported) {
                theme_arena_reported = 1;
                log_line("light theme: image arena full, remaining images stay stock");
            }
            return;
        }
        uint16_t *converted = (uint16_t *)(theme_arena + theme_arena_used);
        unsigned int count = (unsigned int)width * height;
        /* The dark conversion decides per pixel and has no use for the answer,
           so the scan that produces it only runs for the light one. */
        int artwork = theme_light_active ? theme_is_artwork(source, count) : 0;
        for (unsigned int i = 0; i < count; i++)
            converted[i] = theme_light_active
                ? theme_pixel_light_for_image(image, source[i], artwork)
                : theme_pixel_dark(source[i]);
        theme_arena_used += (size_t)bytes;
        moved = (uint32_t)(unsigned long)converted - (uint32_t)(unsigned long)theme_light_table;
        if (theme_seen_count < 4096u) {
            theme_seen_source[theme_seen_count] = source;
            theme_seen_offset[theme_seen_count++] = moved;
        }
    }
    memcpy(theme_light_table + image * 44u + 0x20u, &moved, 4u);
}

static void theme_build_light_table(uint8_t *dark_table)
{
    if (!theme_enabled || theme_light_table || !dark_table) return;
    theme_dark_table = dark_table;
    size_t bytes = EXTENDED_IMAGE_COUNT * 44u;
    theme_light_table = mmap(0, bytes, PROT_READ | PROT_WRITE,
                             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (theme_light_table == MAP_FAILED) { theme_light_table = 0; return; }
    memcpy(theme_light_table, dark_table, bytes);
    uint32_t rebase = (uint32_t)(unsigned long)dark_table -
                      (uint32_t)(unsigned long)theme_light_table;
    for (unsigned int image = 0; image < EXTENDED_IMAGE_COUNT; image++) {
        uint8_t *record = theme_light_table + image * 44u;
        uint32_t offset;
        memcpy(&offset, record + 0x20u, 4u);
        offset += rebase;
        memcpy(record + 0x20u, &offset, 4u);
        if (record[0x19u]) {
            memcpy(&offset, record + 0x24u, 4u);
            offset += rebase;
            memcpy(record + 0x24u, &offset, 4u);
        }
    }
    if (main_logo_light_ready) {
        uint8_t *record = theme_light_table + LOGO_IMAGE_INDEX * 44u;
        uint32_t offset = (uint32_t)(unsigned long)main_logo_light_pixels -
                          (uint32_t)(unsigned long)theme_light_table;
        memcpy(record + 0x20u, &offset, 4u);
    }
    theme_conversion_enabled = 1;
    theme_light_tab_assets();
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

/* Make one page writable, run `change`, and put the protection back.
 *
 * The page has to go back to read-execute whether the write succeeded or not:
 * leaving executable memory writable for the rest of the session is a worse
 * outcome than a pane that stayed dark.
 */
static int theme_write_protected(unsigned long address, size_t span,
                                 void (*change)(void))
{
    long page = sysconf(_SC_PAGESIZE);
    if (page < 1)
        page = 4096;
    unsigned long first = address & ~((unsigned long)page - 1u);
    size_t bytes = (size_t)(address + span - first);
    if (mprotect((void *)first, bytes, PROT_READ | PROT_WRITE))
        return 0;
    change();
    clear_instruction_cache(first, first + bytes);
    return mprotect((void *)first, bytes, PROT_READ | PROT_EXEC) == 0;
}

static int theme_wave_wanted_light;

static void theme_wave_write_table(void)
{
    volatile uint16_t *table = (volatile uint16_t *)THEME_WAVE_TABLE;
    table[THEME_WAVE_INSET_INDEX] = theme_wave_wanted_light
        ? THEME_WAVE_INSET_LIGHT : THEME_WAVE_INSET_DARK;
    table[THEME_WAVE_TINT_INDEX] = theme_wave_wanted_light
        ? THEME_WAVE_TINT_LIGHT : THEME_WAVE_TINT_DARK;
}

static void theme_wave_write_opcode(void)
{
    *(volatile uint32_t *)THEME_WAVE_INSTRUCTION = theme_wave_wanted_light
        ? THEME_WAVE_OPCODE_LIGHT : THEME_WAVE_OPCODE_DARK;
}

/* Put the waveform pane into the mode the rest of the interface is in.
 *
 * The pane keeps a dark ground either way. What changes is how far it is inset
 * and the tint of its own furniture, so that it reads as a well set into a
 * light room rather than as a hole punched in it.
 */
static void theme_waveform_apply(int light)
{
    theme_wave_wanted_light = light;
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
    if (!theme_write_protected(THEME_WAVE_TABLE,
                               THEME_WAVE_TABLE_WORDS * 2u,
                               theme_wave_write_table))
        return;
    if (!theme_write_protected(THEME_WAVE_INSTRUCTION, 4u,
                               theme_wave_write_opcode))
        return;
    /* Both decks, so the change lands without waiting for a track to load. */
    ((void (*)(unsigned int, unsigned int))REFRESH_DECK)(0u, 1u);
    ((void (*)(unsigned int, unsigned int))REFRESH_DECK)(1u, 1u);
}

static int theme_feature_configured(void)
{
    /* Only the setting. configure_features() calls this to decide whether
       install() runs at all, so asking here whether the hook is installed
       would answer no for ever. */
    return theme_enabled;
}

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
    original_hw_fill_rect = (hw_fill_rect_fn)install_hook(
        &hw_fill_rect_hook, HW_FILL_RECT, hw_fill_rect_guard, hooked_hw_fill_rect);
    if (!original_hw_fill_rect)
        return 0;
    /* The fill substitution is the theme; the key hook only turns it on. So a
       key hook that will not install leaves a working feature with no switch,
       which is worth saying and is not worth refusing the feature over. */
    original_send_key = (send_key_fn)install_hook(
        &send_key_hook, SEND_KEY, send_key_guard, hooked_send_key);
    if (!original_send_key)
        log_line("light theme: no live switch, SHIFT+SHORTCUT will not toggle it");
    utility_install_theme_row();
    theme_light_active = 0;
    log_line("light theme: solid fills are ready to be replaced");
    return 1;
}

static void theme_feature_remove(void)
{
    uninstall_hook(&theme_render_pass_hook);
    if (!theme_render_pass_hook.address) original_theme_render_pass = 0;
    utility_remove_theme_row();
    theme_refresh_pending = 0;
    if (theme_dark_table)
        *(uint8_t **)IMAGE_TABLE_POINTER = theme_dark_table;
    if (theme_light_active)
        theme_waveform_apply(0);
    uninstall_hook(&send_key_hook);
    if (!send_key_hook.address) original_send_key = 0;
    uninstall_hook(&hw_fill_rect_hook);
    if (!hw_fill_rect_hook.address) original_hw_fill_rect = 0;
    theme_light_active = 0;
    theme_toggle_pending = 0;
}

#endif /* RX3_THEME_FEATURE_H */
