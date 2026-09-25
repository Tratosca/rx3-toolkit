/* SPDX-License-Identifier: MPL-2.0
 *
 * Where the controls of the performance pad row sit, and what a touch at a
 * given x lands on. One solver answers both questions, because the row used to
 * answer them twice: every panel laid its controls out in its draw and worked
 * out what was hit by repeating the same arithmetic in its touch handler, with
 * nothing keeping the two copies in step.
 *
 * The block between the markers is integer arithmetic over int and nothing
 * else -- no player types, no globals, no libc -- so the test compiles it for
 * the computer and runs it against the preview's copy rather than reading it
 * as text. Keep it that way: a memcpy or a log line in here costs the only
 * verification this row has before it reaches a deck.
 */

#ifndef RX3_PAD_LAYOUT_H
#define RX3_PAD_LAYOUT_H

/* The row, in the pad window's own coordinates. The ground is drawn wider than
   the controls at each end; the controls are what a finger can reach. */
#define RX3_PAD_GROUND_TOP     17
#define RX3_PAD_GROUND_BOTTOM  63
#define RX3_PAD_CTRL_TOP       21
#define RX3_PAD_CTRL_BOTTOM    59
#define RX3_PAD_GROUND_BLEED    4

/* One deck's half, and the whole screen for a control that spans both. */
#define RX3_PAD_DECK_ORIGIN    19
#define RX3_PAD_DECK_SPAN     595
#define RX3_PAD_SCREEN_ORIGIN  20
#define RX3_PAD_SCREEN_SPAN  1240
#define RX3_PAD_DECK_STRIDE   640

/* A drawn control at local y 21 is touched at screen y 521, and both are 39
   tall. The touch band is derived from the drawn control through this one
   number rather than written down a second time, because the two literals
   disagreeing by a few pixels is a dead strip along one edge of every control
   that nothing would ever report. */
#define RX3_PAD_LOCAL_TO_SCREEN_Y 500
#define RX3_PAD_TOUCH_TOP    (RX3_PAD_CTRL_TOP    + RX3_PAD_LOCAL_TO_SCREEN_Y)
#define RX3_PAD_TOUCH_BOTTOM (RX3_PAD_CTRL_BOTTOM + RX3_PAD_LOCAL_TO_SCREEN_Y)

/* RX3 PAD LAYOUT BEGIN */
#define RX3_PAD_CELL_MAX 8

/* A stepper's arrow ends: a quarter of the cell, held between these so a narrow
   stepper keeps a readable value and a wide one does not grow two huge arrows. */
#define RX3_PAD_STEP_END_MIN   40
#define RX3_PAD_STEP_END_MAX   96
#define RX3_PAD_STEP_INNER_GAP  6
#define RX3_PAD_STEP_VALUE_MIN 16

struct rx3_pad_cell { int x1, x2; };

/* The gap between controls, by how many there are.
 *
 * The first five entries are the stems strip's own, measured on the row rather
 * than derived, and solving with them reproduces its widths exactly: 595, 288,
 * 187 and 139. That is not a coincidence in the original -- each gap was picked
 * so the width left over divides exactly, 576 by two, 561 by three, 556 by
 * four -- but a solver cannot count on it for a count nobody chose a gap for,
 * so it spreads the remainder instead. Past five the shape simply continues.
 */
static const int rx3_pad_gap[RX3_PAD_CELL_MAX + 1] = {
    0, 0, 19, 17, 13, 11, 11, 9, 9
};

/* Lay count cells across span, in proportion to their weights.
 *
 * Every division here is unsigned on purpose. Signed division on this target is
 * a call to __aeabi_idiv, which rbp does not export and tests/test_hook_symbols
 * would refuse; __aeabi_uidiv is the one that is available.
 */
static int rx3_pad_solve(const unsigned char *weights, int count,
                         int origin, int span, struct rx3_pad_cell *out)
{
    int i, x, shares = 0, free_width, gap;
    unsigned int unit, spare;

    if (count <= 0 || count > RX3_PAD_CELL_MAX || !weights || !out)
        return 0;
    gap = rx3_pad_gap[count];
    free_width = span - gap * (count - 1);
    if (free_width < count)
        return 0;
    for (i = 0; i < count; i++)
        shares += weights[i] ? (int)weights[i] : 1;
    unit = (unsigned int)free_width / (unsigned int)shares;
    spare = (unsigned int)free_width - unit * (unsigned int)shares;

    x = origin;
    for (i = 0; i < count; i++) {
        int weight = weights[i] ? (int)weights[i] : 1;
        int width = (int)unit * weight;
        /* The pixels that did not divide go to the last cells, so the row ends
           on origin + span - 1 whatever the count and nothing shifts under a
           finger already resting on the control at the end. */
        if (i >= count - (int)spare)
            width++;
        out[i].x1 = x;
        out[i].x2 = x + width - 1;
        x += width + gap;
    }
    return count;
}

/* A stepper is one declared widget and three touchable parts: decrement, the
   value, increment. */
static void rx3_pad_stepper_parts(struct rx3_pad_cell cell,
                                  struct rx3_pad_cell *parts)
{
    int width = cell.x2 - cell.x1 + 1;
    int end = width >> 2;

    if (end < RX3_PAD_STEP_END_MIN) end = RX3_PAD_STEP_END_MIN;
    if (end > RX3_PAD_STEP_END_MAX) end = RX3_PAD_STEP_END_MAX;
    if (end * 2 + RX3_PAD_STEP_INNER_GAP * 2 + RX3_PAD_STEP_VALUE_MIN > width) {
        end = (width - RX3_PAD_STEP_INNER_GAP * 2 - RX3_PAD_STEP_VALUE_MIN) >> 1;
        if (end < 8) end = 8;
    }
    parts[0].x1 = cell.x1;
    parts[0].x2 = cell.x1 + end - 1;
    parts[2].x2 = cell.x2;
    parts[2].x1 = cell.x2 - end + 1;
    parts[1].x1 = parts[0].x2 + 1 + RX3_PAD_STEP_INNER_GAP;
    parts[1].x2 = parts[2].x1 - 1 - RX3_PAD_STEP_INNER_GAP;
}

/* Which cell an x lands on, or -1 for the gap between two. The gaps are not
   dead by accident: a finger there is handed back to the player, which is what
   parking the native touch areas exists to make safe. */
static int rx3_pad_hit(const struct rx3_pad_cell *cells, int count, int x)
{
    int i;
    for (i = 0; i < count; i++)
        if (x >= cells[i].x1 && x <= cells[i].x2)
            return i;
    return -1;
}

/* Where a slider sits when the finger is at x, rounded to nearest.
 *
 * The released control's own mapping was ((x * 100) - 1536) / 1128, fitted to
 * one track at one width. This is the same shape stated in terms of the cell,
 * so a slider of any width lands on 0 at its left edge and max at its right.
 */
static int rx3_pad_slider_value(struct rx3_pad_cell cell, int x, int max)
{
    int width = cell.x2 - cell.x1 + 1;
    unsigned int travel, offset;

    if (max <= 0 || width <= 1)
        return 0;
    if (x <= cell.x1) return 0;
    if (x >= cell.x2) return max;
    travel = (unsigned int)(width - 1);
    offset = (unsigned int)(x - cell.x1);
    return (int)((offset * (unsigned int)max + travel / 2u) / travel);
}

/* The inverse, for drawing the filled part of a track. */
static int rx3_pad_slider_x(struct rx3_pad_cell cell, int value, int max)
{
    int width = cell.x2 - cell.x1 + 1;
    unsigned int travel;

    if (max <= 0 || width <= 1)
        return cell.x1;
    if (value <= 0) return cell.x1;
    if (value >= max) return cell.x2;
    travel = (unsigned int)(width - 1);
    return cell.x1 + (int)(((unsigned int)value * travel +
                            (unsigned int)max / 2u) / (unsigned int)max);
}
/* RX3 PAD LAYOUT END */

#endif /* RX3_PAD_LAYOUT_H */
