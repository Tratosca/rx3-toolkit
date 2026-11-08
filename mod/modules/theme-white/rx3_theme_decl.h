/* SPDX-License-Identifier: MPL-2.0
 * Private light theme state and the player structures it reaches into.
 * Which image table is shown, and the fill adapter, belong to the core's
 * image service; this module supplies the policy and decides when to switch.
 */

#ifndef RX3_THEME_DECL_H
#define RX3_THEME_DECL_H

/* The global dark remap: the stock chrome taken down rather than inverted. It
   is a mode of its own, not the absence of the light one, and it runs the
   conversion in theme_pixel_dark over the same image table. */
static int theme_global_dark;
/* Its kill switch. The watcher polls for it, so a set that goes wrong can be
   put back to stock without a restart. */
#define THEME_DARK_SENTINEL "/tmp/rx3-theme.off"

/* The fill colour the core's adapter hands over. Three channels in one word:
 * blue at bits 0..4, green at 8..13, red at 16..20. Green carries six bits
 * where the others carry five, which is why a comparison across all three
 * shifts it down by one first.
 */
#define THEME_FILL_BLUE_SHIFT  0u
#define THEME_FILL_GREEN_SHIFT 8u
#define THEME_FILL_RED_SHIFT   16u

/* What a dark neutral fill is replaced by. Read as channels, the first is
 * about #d0 and the second about #e0: the ground the interface sits on, and
 * the panels that sit on the ground.
 */
#define THEME_FILL_GROUND 0x001a341au
#define THEME_FILL_PANEL  0x001c381cu

/* Only a fill that is already dark and close to neutral is replaced. Anything
 * brighter is a deliberate colour, and anything with a spread across channels
 * is carrying meaning: a status, a warning, an artwork edge. Recolouring those
 * is how a light theme turns into a broken one.
 */
#define THEME_FILL_MAX_CHANNEL 0x0bu
#define THEME_FILL_MAX_SPREAD  2u

/* Rectangles the player draws for whole panes. Anything smaller than the area
 * below is a control rather than a pane, and takes the panel colour.
 */
#define THEME_PANE_MIN_AREA 300000u
#define THEME_PANE_WIDE     0x444u
#define THEME_PANE_NARROW   0x43bu
#define THEME_PANE_MID      0x410u
#define THEME_PANE_SHORT    0x37cu
#define THEME_PANE_TALL     0x20du
#define THEME_PANE_MEDIUM   0x212u
#define THEME_PANE_LOW      0x202u
#define THEME_PANE_SHALLOW  0x1bcu

/* The key that completes SHIFT + SHORTCUT. The core's input service tracks
 * SHIFT per channel, because the player reports it as an ordinary key.
 */
#define THEME_KEY_SHORTCUT 0x0210u
/* Key operations, as the player numbers them. A release arrives as either of
 * the two values above one, which is why the test masks the low bit away.
 */
#define THEME_KEY_PRESS 0u
#define THEME_KEY_RELEASE 2u

/* The first two instructions are position-independent on firmware 1.19/1.20. */
#define THEME_RENDER_PASS ((unsigned long)0x001d48a0)
static const uint8_t theme_render_pass_guard[8] = {
    0x38, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};

/* Native window invalidation, called once at a theme transition. */
#define THEME_DIRTY_WINDOWS ((unsigned long)0x001d1144)
static const uint8_t theme_dirty_windows_guard[8] = {
    0xf8, 0x40, 0x2d, 0xe9, 0xcc, 0x40, 0x9f, 0xe5
};

/* ui_Counter_DrawCautionWindow (0x002863f8) repaints a deck strip's message
   ("Not Loaded.") and its filled backing only when the deck's caution ID, state
   or language changes, so a theme switch alone leaves the old backing. The
   guard is its movw/movt loading the cache base 0x00526850; the caution IDs are
   at +8, one word per deck. */
#define THEME_COUNTER_CAUTION_CACHE ((unsigned long)0x00286420)
static const uint8_t theme_counter_caution_cache_guard[8] = {
    0x50, 0x28, 0x06, 0xe3, 0x52, 0x20, 0x40, 0xe3
};
#define THEME_COUNTER_CAUTION_IDS ((unsigned long)0x00526858)

/* ui_com_draw_ShowScreen: activates a winscape by ID (0 is the main screen,
   what the start screen hands over to). Entering a winscape reloads its
   resources, which recreates and clears every window it owns. */
#define THEME_SHOW_SCREEN ((unsigned long)0x0018e024)
static const uint8_t theme_show_screen_guard[8] = {
    0x10, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};

/* ui_CTRL_SIMPLE_COUNTER_Clear: BROWSE's independent counter windows can
   survive a HOME winscape reload. Its 400x60 caution boxes and five margin
   windows (IDs 227..231, y709..789) then cover the newly painted HOME.
   Use the same teardown as the native switch back to full counters. */
#define THEME_SIMPLE_COUNTER_CLEAR ((unsigned long)0x002b5780)
static const uint8_t theme_simple_counter_clear_guard[8] = {
    0xf8, 0x45, 0x2d, 0xe9, 0x4c, 0x42, 0x9f, 0xe5
};

/* DS_HW_ClearScreen: fills the screen surface of each display layer with the
   layer's colour. The player calls it once, when it sets the resolution at
   start; keyed windows show that surface wherever they are transparent. */
#define THEME_CLEAR_SCREEN ((unsigned long)0x001ab900)
static const uint8_t theme_clear_screen_guard[8] = {
    0x70, 0x40, 0x2d, 0xe9, 0x10, 0x00, 0xc0, 0xf2
};

/* DS_HW_FillRect(window, x, y, width | height << 16): fills part of one
   window with the window's colour and marks the area for the next update. */
#define THEME_HW_FILL_RECT ((unsigned long)0x001a85f4)
static const uint8_t theme_hw_fill_rect_guard[8] = {
    0x30, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
/* Display layer 0 and its window records, as DS_HW_UpdateScreen reads them.
   The base is the literal that function loads; it is checked before use. */
#define THEME_LAYER0 0x0245b810ul
#define THEME_LAYER0_LITERAL 0x001a6924ul
#define THEME_LAYER_WINDOWS 0x70u
#define THEME_WINDOW_WIDTH 0x08u
#define THEME_WINDOW_HEIGHT 0x0au
#define THEME_WINDOW_COLOUR 0x28u
#define THEME_WINDOW_Y 0x58u
#define THEME_WINDOW_NEXT 0x84u
#define THEME_WINDOW_WALK_LIMIT 400u
#define THEME_MARGIN_MAX_WIDTH 20u
#define THEME_MARGIN_TOP 709
#define THEME_MARGIN_BOTTOM 789
#define THEME_MARGIN_REPAINT_PASSES 3u

#define THEME_COMPONENT_MANAGER ((unsigned long)0x001d0a30)
static const uint8_t theme_component_manager_guard[8] = {
    0x10, 0x40, 0x2d, 0xe9, 0x20, 0x40, 0x9f, 0xe5
};
#define THEME_ACTIVE_WINSCAPE ((unsigned long)0x001cc510)
static const uint8_t theme_active_winscape_guard[8] = {
    0x20, 0x00, 0x90, 0xe5, 0x1e, 0xff, 0x2f, 0xe1
};

/* ui_com_draw_RefreshObject queues a single native control for repaint.
   ui_Utility_SetText (0x002952e8) uses this row-name ID table; its first
   twelve entries are the names currently visible in UTILITY. */
#define THEME_REFRESH_OBJECT ((unsigned long)0x0018e1a0)
static const uint8_t theme_refresh_object_guard[8] = {
    0x70, 0x40, 0x2d, 0xe9, 0x00, 0x40, 0xa0, 0xe1
};
#define THEME_UTILITY_NAME_IDS ((unsigned long)0x004c97e8)
static const uint8_t theme_utility_name_ids_guard[8] = {
    0x8c, 0x00, 0x87, 0x00, 0x82, 0x00, 0x7d, 0x00
};
/* ui_Utility_SetText passes this control root to GetObjectByID, rather than
   searching the active winscape root. */
#define THEME_UTILITY_ROOT_LITERAL ((unsigned long)0x00295524)
static const uint8_t theme_utility_root_literal_guard[8] = {
    0x10, 0x46, 0x68, 0x02, 0xb8, 0x97, 0x4c, 0x00
};
#define THEME_UTILITY_ROOT_PTR ((unsigned long)0x02684610)

/* Magenta. The player writes every other value to the framebuffer and skips
 * this one, so it is transparency and never a colour. Converting it would
 * punch a hole in whatever image it belongs to.
 *
 * The same value is in tools/rx3_logo/container.py, which writes containers
 * this reads; the logo module's guard compares the two.
 */
#define COLOUR_KEY 0xf81fu

/* The renderer allocates once after checking free memory, then stops growing
   the arena. Allocation failure disables further image conversion. */
#define THEME_ARENA_BYTES (10u * 1024u * 1024u)
#define THEME_ARENA_FLOOR_KB (128u * 1024u)
#define THEME_CONVERT_RESERVE_KB (48u * 1024u)
#define THEME_IMAGE_MAX_BYTES (4u * 1024u * 1024u)

/* Direct colour, no palette. Only these are converted: a paletted bitmap needs
 * its palette converted instead, and that is shared between images.
 */
#define THEME_FORMAT_RGB565 1u
#define THEME_FORMAT_RGB565_KEYED 2u

/* At least this share of the opaque pixels must be vivid for a bitmap to count
 * as artwork and keep its hue. Below it the bitmap is chrome, and chrome is
 * what the theme exists to repaint.
 */
#define THEME_ARTWORK_PERCENT 25u
/* How far apart the channels must be for one pixel to count as vivid. */
#define THEME_VIVID_SPREAD 0x37u

/* The dark conversion is decided on a tighter spread than anything above: a
   pixel is taken down only if it is already grey. */
#define THEME_DARK_SPREAD 0x17u
/* One multiplier for all three channels, each shifted to land in its own
   field. It works out at roughly a third of the original brightness. */
#define THEME_DARK_SCALE 0x2ccd1u

/* Weights summing to 256, so the luma is a shift rather than a division. */
#define THEME_LUMA_RED 0x36u
#define THEME_LUMA_GREEN 0xb7u
#define THEME_LUMA_BLUE 0x13u
/* Nothing in the light interface is brighter than this, so a colour above it
 * is scaled down rather than left to glare against a pale ground.
 */
#define THEME_LUMA_CEILING 0x66u
/* Chrome is folded into this range, inverted: what was near black becomes near
 * white, and the ends stay off the extremes so the panes keep their edges.
 */
#define THEME_GREY_FLOOR 0x30u
#define THEME_GREY_SPAN 0xb0u
/* Below the first spread a pixel is neutral and fully inverted; above the
 * second it is treated as artwork; between them the two are blended.
 */
#define THEME_NEUTRAL_SPREAD 0x19u
#define THEME_LIGHT_SPREAD 0x38u

/* The blend, exactly. One spread step is eight parts in two hundred and
 * fifty-six, counted from one below the neutral threshold, so a pixel that has
 * only just stopped being neutral keeps almost none of its colour and one that
 * is about to count as artwork keeps almost all of it.
 *
 * Two hundred and fifty-six and not two hundred and fifty-five: the products
 * are masked straight into the colour fields, so the total has to be a power
 * of two or every blended pixel is off by a fraction of a step.
 */
#define THEME_BLEND_BASE 0x18u
#define THEME_BLEND_STEP 8u
#define THEME_BLEND_TOTAL 0x100u

/* The waveform pane is not remapped like the rest of the interface. It stays a
 * dark well whichever mode the room is in, because a waveform read at a glance
 * needs contrast against its own background and not against the furniture.
 *
 * Two entries of the pane's own palette change, and one instruction that
 * chooses how far the pane is inset. Everything else in the table is checked
 * and left alone, so a firmware whose table is not this one is not written to.
 */
#define THEME_WAVE_TABLE ((unsigned long)0x004422f8)
#define THEME_WAVE_TABLE_WORDS 8u
#define THEME_WAVE_INSET_INDEX 3u
#define THEME_WAVE_TINT_INDEX 6u
#define THEME_WAVE_INSET_DARK 0x02bcu
#define THEME_WAVE_INSET_LIGHT 0x04feu
#define THEME_WAVE_TINT_DARK 0xb341u
#define THEME_WAVE_TINT_LIGHT 0xc461u

/* One instruction, rewritten in place: `mov r1, #0` for dark and `mov r1,
 * #0x4a` for light. Guarded the same way a hook prologue is, so an address
 * that is not this instruction is left alone.
 */
#define THEME_WAVE_INSTRUCTION ((unsigned long)0x0024fed0)
#define THEME_WAVE_OPCODE_DARK 0xe3a01000u
#define THEME_WAVE_OPCODE_LIGHT 0xe3a0104au

/* Asks the player to draw one deck again, so the pane picks the change up
 * without waiting for the next track.
 */
#define REFRESH_DECK ((unsigned long)0x001856fc)

#define THEME_HEADER_CONTROL ((unsigned long)0x02684400)
/* Queue one glyph for repaint, from the render thread. */
#define GET_HMI_MANAGER ((unsigned long)0x001d09b4)
#define REFRESH_GLYPH   ((unsigned long)0x001d07b0)
/* Stock records the conversion may be asked for. */
#define STOCK_IMAGE_COUNT RX3_NATIVE_IMAGE_COUNT

#endif /* RX3_THEME_DECL_H */
