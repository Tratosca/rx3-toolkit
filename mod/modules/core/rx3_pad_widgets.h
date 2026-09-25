/* SPDX-License-Identifier: MPL-2.0
 *
 * The pad row: one painter and one touch machine, for every panel.
 *
 * Both walk the same rectangles, solved once by rx3_pad_layout.h. That is the
 * whole reason this file exists. Before it, a panel drew its controls from one
 * set of numbers and decided what a finger had hit from another copy of them,
 * and nothing anywhere made the two agree.
 *
 * The touch machine is what makes a control feel like a button. A press marks
 * it and paints it; sliding off cancels without firing; sliding back on
 * restores it; only a release still inside it fires. A control that acted on
 * contact would fire the moment a thumb brushed past on its way somewhere else.
 */

#ifndef RX3_PAD_WIDGETS_H
#define RX3_PAD_WIDGETS_H

/* What is under the finger, and whether it is still under it. */
static volatile int pad_press_deck = -1;
static volatile int pad_press_widget = -1;
static volatile int pad_press_part = -1;
static volatile unsigned int pad_press_inside;
static volatile unsigned int pad_drag_active;

static unsigned int pad_row_live_count(const struct rx3_pad_row *row,
                                       unsigned int deck)
{
    unsigned int count = row->live_count ? row->live_count(deck) : row->count;
    if (count > row->count) count = row->count;
    if (count > RX3_PAD_CELL_MAX) count = RX3_PAD_CELL_MAX;
    return count ? count : 1u;
}

/* Solve one deck's row. Cells come back in screen x, so a hit test and a draw
   are talking about the same pixels whatever the scope. */
static int pad_row_cells(const struct rx3_pad_row *row, unsigned int deck,
                         struct rx3_pad_cell *cells)
{
    unsigned char weights[RX3_PAD_CELL_MAX];
    unsigned int i, count = pad_row_live_count(row, deck);
    int origin, span, base, solved;

    for (i = 0; i < count; i++)
        weights[i] = row->widgets[i].weight;
    if (row->scope == RX3_PAD_SCOPE_SCREEN) {
        origin = RX3_PAD_SCREEN_ORIGIN;
        span = RX3_PAD_SCREEN_SPAN;
        base = 0;
    } else {
        origin = RX3_PAD_DECK_ORIGIN;
        span = RX3_PAD_DECK_SPAN;
        base = (int)deck * RX3_PAD_DECK_STRIDE;
    }
    solved = rx3_pad_solve(weights, (int)count, origin, span, cells);
    for (i = 0; i < (unsigned int)solved; i++) {
        cells[i].x1 += base;
        cells[i].x2 += base;
    }
    return solved;
}

/* The rectangles of one widget: one for most, three for a stepper. */
static int pad_widget_parts(const struct rx3_pad_row *row, unsigned int widget,
                            struct rx3_pad_cell cell, struct rx3_pad_cell *parts)
{
    if (row->widgets[widget].kind == RX3_PAD_STEPPER) {
        rx3_pad_stepper_parts(cell, parts);
        return 3;
    }
    parts[0] = cell;
    return 1;
}

/* Which ground a part is drawn on. A press takes the pressed artwork and a
   lit control the selected artwork; a press on something already lit stays
   lit, because the state a DJ is reading matters more than the finger. */
static unsigned int pad_part_ink(const struct rx3_pad_row *row,
                                 unsigned int deck, unsigned int widget,
                                 unsigned int part)
{
    if (row->is_on && row->is_on(deck, widget, part))
        return RX3_PAD_INK_SELECTED;
    if ((int)deck == pad_press_deck && (int)widget == pad_press_widget &&
        (int)part == pad_press_part && pad_press_inside)
        return RX3_PAD_INK_PRESSED;
    return RX3_PAD_INK_INACTIVE;
}

static void draw_native_image_local(void *render, const void *model,
                                    uint8_t target_window,
                                    int x1, int y1, int x2, int y2,
                                    uint32_t image_id);

/* Cells are solved in screen x, so a hit test can use them as they are. A draw
   cannot: each deck's window is its own 640 wide surface and a box is placed in
   that window's coordinates. So a box crosses into deck-local here and is
   clipped to the half being painted, which is how one control spanning both
   halves is drawn twice, once into each, and how it stops at the seam. */
static int pad_local_box(unsigned int deck, int *x1, int *x2)
{
    int base = (int)deck * RX3_PAD_DECK_STRIDE;
    int left = *x1 - base, right = *x2 - base;

    if (right < 0 || left > RX3_PAD_DECK_STRIDE - 1)
        return 0;
    if (left < 0) left = 0;
    if (right > RX3_PAD_DECK_STRIDE - 1) right = RX3_PAD_DECK_STRIDE - 1;
    *x1 = left;
    *x2 = right;
    return 1;
}

/* One caption, centred, one image per character.
 *
 * Centring is a halving rather than a division: this arm has no integer divide
 * instruction, so a division here is a call, and the row draws a lot of these.
 */
static void pad_draw_caption(void *render, const void *model, uint8_t window,
                             unsigned int deck, struct rx3_pad_cell cell,
                             const uint16_t *text, unsigned int ink)
{
    int pen, top, slack;
    unsigned int width;

    if (!text || !*text || !pad_atlas_ready)
        return;
    width = pad_atlas_text_width(text);
    slack = (cell.x2 - cell.x1 + 1) - (int)width;
    if (slack < 0)
        slack = 0;              /* too long for its cell: start at the left */
    pen = cell.x1 + (slack >> 1);
    top = RX3_PAD_CTRL_TOP +
          ((RX3_PAD_CTRL_BOTTOM - RX3_PAD_CTRL_TOP + 1 -
            (int)pad_atlas.cell_height) >> 1);

    while (*text) {
        unsigned int codepoint = *text++;
        unsigned int cell_width = pad_atlas_cell_width(codepoint);
        if (cell_width) {
            /* The glyph origin sits ink_left into its cell, so the cell is
               drawn that far back for the letter to land on the pen. */
            int left = pen - (int)pad_atlas.ink_left;
            int right = left + (int)cell_width - 1;
            /* A letter is drawn whole or not at all. Half a glyph at the seam
               between the two windows is worse than the gap, and no caption
               crosses it. */
            if (pad_local_box(deck, &left, &right) &&
                right - left == (int)cell_width - 1)
                draw_native_image_local(
                    render, model, window, left, top,
                    right, top + (int)pad_atlas.cell_height - 1,
                    pad_atlas_image_id(codepoint, ink));
        }
        pen += (int)pad_atlas_advance(codepoint);
    }
}

/* A filled rectangle in one of the artwork's own grounds. */
static void pad_fill(void *render, const void *model, uint8_t window,
                     unsigned int deck, int x1, int y1, int x2, int y2,
                     uint32_t colour)
{
    const void *face = pad_button_face();
    /* No face captured yet means no model to cut a box from. The lettering is
       artwork and does not need one, so the row draws its captions and skips
       its fills rather than standing down altogether. */
    if (!face || x2 < x1 || !pad_local_box(deck, &x1, &x2))
        return;
    draw_native_box_local(render, face, model, window,
                          x1, y1, x2, y2, text_empty, PAD_COLOUR_INHERIT, colour);
}

static void pad_draw_slider(void *render, const void *model, uint8_t window,
                            const struct rx3_pad_row *row, unsigned int deck,
                            unsigned int widget, struct rx3_pad_cell cell)
{
    unsigned int maximum = row->slider_max ? row->slider_max(deck, widget) : 100u;
    unsigned int value = row->slider_get ? row->slider_get(deck, widget) : 0u;
    int filled;

    if (value > maximum)
        value = maximum;
    /* A one pixel frame in the selected colour, so an empty track is still a
       track and not a hole in the row. */
    pad_fill(render, model, window, deck, cell.x1, RX3_PAD_CTRL_TOP,
             cell.x2, RX3_PAD_CTRL_BOTTOM,
             pad_atlas_ground_colour(RX3_PAD_INK_SELECTED));
    pad_fill(render, model, window, deck, cell.x1 + 1, RX3_PAD_CTRL_TOP + 1,
             cell.x2 - 1, RX3_PAD_CTRL_BOTTOM - 1,
             pad_atlas_ground_colour(RX3_PAD_INK_INACTIVE));
    filled = rx3_pad_slider_x(cell, (int)value, (int)maximum);
    if (filled > cell.x1)
        pad_fill(render, model, window, deck, cell.x1 + 1, RX3_PAD_CTRL_TOP + 1,
                 filled, RX3_PAD_CTRL_BOTTOM - 1,
                 pad_atlas_ground_colour(RX3_PAD_INK_SELECTED));
}

/* One deck's half of the row. */
static void pad_row_paint(void *render, const void *model, uint8_t window,
                          unsigned int deck, const struct rx3_pad_row *row)
{
    struct rx3_pad_cell cells[RX3_PAD_CELL_MAX], parts[3];
    int count, i, part, parts_count;
    int left, right;

    count = pad_row_cells(row, deck, cells);
    if (count <= 0)
        return;

    /* The ground the controls sit on, wider than they are at each end. It is
       what carries the room's colour; a control only ever paints its own box. */
    left = cells[0].x1 - RX3_PAD_GROUND_BLEED;
    right = cells[count - 1].x2 + RX3_PAD_GROUND_BLEED;
    pad_fill(render, model, window, deck, left, RX3_PAD_GROUND_TOP,
             right, RX3_PAD_GROUND_BOTTOM,
             pad_atlas_ground_colour(RX3_PAD_INK_INACTIVE));

    for (i = 0; i < count; i++) {
        if (row->widgets[i].kind == RX3_PAD_SLIDER) {
            pad_draw_slider(render, model, window, row, deck,
                            (unsigned int)i, cells[i]);
            continue;
        }
        parts_count = pad_widget_parts(row, (unsigned int)i, cells[i], parts);
        for (part = 0; part < parts_count; part++) {
            unsigned int ink = pad_part_ink(row, deck, (unsigned int)i,
                                            (unsigned int)part);
            /* An inactive control shares the row's ground, so filling it again
               would be a rectangle of the same colour: only a lit or pressed
               one needs a box of its own. */
            if (ink != RX3_PAD_INK_INACTIVE)
                pad_fill(render, model, window, deck, parts[part].x1, RX3_PAD_CTRL_TOP,
                         parts[part].x2, RX3_PAD_CTRL_BOTTOM,
                         pad_atlas_ground_colour(ink));
            pad_draw_caption(render, model, window, deck, parts[part],
                             row->caption ? row->caption(deck, (unsigned int)i,
                                                         (unsigned int)part) : 0,
                             ink);
        }
    }
}

/* Ask for a repaint. Never paint from here: this runs on the input path, and
   the renderer's own thread drains this flag and holds the refresh window. */
static void pad_row_invalidate(void)
{
    __atomic_store_n(&performance_refresh_pending, 1u, __ATOMIC_SEQ_CST);
}

static void pad_row_clear_press(void)
{
    pad_press_deck = -1;
    pad_press_widget = -1;
    pad_press_part = -1;
    pad_press_inside = 0u;
    pad_drag_active = 0u;
}

/* Find the widget and part under a screen x, or say there is none. */
static int pad_row_locate(const struct rx3_pad_row *row, unsigned int deck,
                          int x, unsigned int *widget, unsigned int *part)
{
    struct rx3_pad_cell cells[RX3_PAD_CELL_MAX], parts[3];
    int count = pad_row_cells(row, deck, cells);
    int found = rx3_pad_hit(cells, count, x);
    int parts_count, index;

    if (found < 0)
        return 0;
    parts_count = pad_widget_parts(row, (unsigned int)found, cells[found], parts);
    index = rx3_pad_hit(parts, parts_count, x);
    if (index < 0)
        return 0;               /* the space between a stepper's parts */
    *widget = (unsigned int)found;
    *part = (unsigned int)index;
    return 1;
}

static void pad_row_slide(const struct rx3_pad_row *row, unsigned int deck,
                          int x, unsigned int committed)
{
    struct rx3_pad_cell cells[RX3_PAD_CELL_MAX];
    unsigned int widget = (unsigned int)pad_press_widget, maximum, value;
    int count = pad_row_cells(row, deck, cells);

    if (pad_press_widget < 0 || pad_press_widget >= count || !row->slider_set)
        return;
    maximum = row->slider_max ? row->slider_max(deck, widget) : 100u;
    value = (unsigned int)rx3_pad_slider_value(cells[widget], x, (int)maximum);
    /* Only a real move is worth a repaint: a drag reports far faster than the
       row is redrawn, and re-arming the refresh window on every report would
       hold it open for as long as a finger is down. */
    if (!committed && row->slider_get && row->slider_get(deck, widget) == value)
        return;
    row->slider_set(deck, widget, value, committed);
    pad_row_invalidate();
}

/* The row's whole input contract. Phases are release 0, press 1 and drag 2,
   with x relative to the deck that captured the press. Returning 0 on a press
   leaves the touch to the player, which is what the gaps between controls are
   for. */
static int pad_row_touch(const struct rx3_pad_row *row, unsigned int deck,
                         int x, unsigned int phase)
{
    unsigned int widget = 0, part = 0;
    int screen_x = x + (int)deck * RX3_PAD_DECK_STRIDE;

    if (!row)
        return 0;

    if (phase == 1u) {
        if (!pad_row_locate(row, deck, screen_x, &widget, &part))
            return 0;
        pad_press_deck = (int)deck;
        pad_press_widget = (int)widget;
        pad_press_part = (int)part;
        pad_press_inside = 1u;
        if (row->widgets[widget].kind == RX3_PAD_SLIDER) {
            /* Tapping the track is the first event of a drag, not a case of
               its own: the value follows the finger from the moment it lands. */
            pad_drag_active = 1u;
            pad_row_slide(row, deck, screen_x, 0u);
        }
        pad_row_invalidate();
        return 1;
    }

    if (pad_press_deck < 0)
        return 0;

    if (phase == 2u) {
        if (pad_drag_active) {
            pad_row_slide(row, deck, screen_x, 0u);
        } else {
            unsigned int over = 0u;
            if (pad_row_locate(row, deck, screen_x, &widget, &part) &&
                (int)widget == pad_press_widget && (int)part == pad_press_part)
                over = 1u;
            if (over != pad_press_inside) {
                pad_press_inside = over;
                pad_row_invalidate();
            }
        }
        return 1;
    }

    /* Release. */
    if (pad_drag_active) {
        pad_row_slide(row, deck, screen_x, 1u);
    } else if (pad_press_inside && row->fire) {
        row->fire((unsigned int)pad_press_deck, (unsigned int)pad_press_widget,
                  (unsigned int)pad_press_part);
    }
    pad_row_clear_press();
    pad_row_invalidate();
    return 1;
}

#endif /* RX3_PAD_WIDGETS_H */
