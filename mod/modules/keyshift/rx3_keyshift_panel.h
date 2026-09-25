/* SPDX-License-Identifier: MPL-2.0
 * Key Shift implementation of the core feature-panel contract.
 */

#ifndef RX3_KEYSHIFT_PANEL_H
#define RX3_KEYSHIFT_PANEL_H

#include "rx3_keyshift_text.h"

static int keyshift_track_key[2] = {-1, -1};
static uint16_t keyshift_labels[2][3][12];

/* Where a deck sits on the wheel right now, shift included. */
static int keyshift_current_key(unsigned int deck)
{
    if (deck >= 2u) return -1;
    return rx3_camelot_shifted(keyshift_track_key[deck],
                               rx3_keyshift_semitones(deck));
}

/* The shift that would bring this deck into key with the other one.
 *
 * Zero when they already mix, when either key is unknown, or when nothing
 * inside the shifter's own range reaches. The search runs outward from where
 * the deck is now rather than from nothing, so the answer is the smallest move
 * from here and not the smallest move in the abstract: a DJ mid-blend wants
 * the nearest key, not the tidiest one.
 */
static int keyshift_match_delta(unsigned int deck)
{
    if (deck >= 2u) return 0;
    int mine = keyshift_track_key[deck];
    int theirs = keyshift_current_key(deck ^ 1u);
    int now = rx3_keyshift_semitones(deck);
    int here = rx3_camelot_shifted(mine, now);
    if (here < 0 || theirs < 0 || rx3_camelot_compatible(here, theirs))
        return 0;
    for (int distance = 1; distance <= 24; distance++)
        for (int sign = 1; sign >= -1; sign -= 2) {
            int candidate = now + sign * distance;
            if (candidate < -12 || candidate > 12) continue;
            if (rx3_camelot_compatible(rx3_camelot_shifted(mine, candidate), theirs))
                return candidate - now;
        }
    return 0;
}

/* The three strings the row shows are indexed the way the stepper's parts are:
   decrement, value, increment. keyshift_format_labels already writes them in
   that order, so nothing here has to be rearranged. */
static const uint16_t *keyshift_caption(unsigned int deck, unsigned int widget,
                                        unsigned int part)
{
    (void)widget;
    if (deck >= 2u || part >= 3u) return keyshift_labels[0][1];
    keyshift_format_labels(keyshift_labels[deck], keyshift_track_key[deck],
                           rx3_keyshift_semitones(deck),
                           keyshift_match_delta(deck));
    return keyshift_labels[deck][part];
}

static void keyshift_capture_text(const uint8_t *glyph)
{
    if (!keyshift_enabled) return;
    uint16_t layer, box[4];
    memcpy(&layer, glyph + 0x10u, 2u);
    memcpy(box, glyph + 0x18u, sizeof(box));
    int deck = keyshift_text_deck(layer, box[0], box[1], box[2], box[3]);
    if (deck < 0) return;
    const uint16_t *text;
    memcpy(&text, glyph + 0x34u, sizeof(text));
    int key = keyshift_key_from_glyph_text(text, glyph[0x38u]);
    if (key == keyshift_track_key[deck]) return;
    keyshift_track_key[deck] = key;
    if (overlay_panel == 1u)
        __atomic_store_n(&performance_refresh_pending, 1u, __ATOMIC_SEQ_CST);
}

/* Lit when the two decks mix, so being in key is something a DJ glances at
   rather than works out. With only one key on screen there is nothing to be in
   key with, and the value falls back to marking an unshifted deck. */
static int keyshift_is_on(unsigned int deck, unsigned int widget,
                          unsigned int part)
{
    (void)widget;
    if (part != 1u) return 0;
    int here = keyshift_current_key(deck);
    int theirs = keyshift_current_key(deck ^ 1u);
    if (here >= 0 && theirs >= 0)
        return rx3_camelot_compatible(here, theirs);
    return rx3_keyshift_semitones(deck) == 0;
}

static void keyshift_fire(unsigned int deck, unsigned int widget,
                          unsigned int part)
{
    (void)widget;
    if (part == 0u) {
        rx3_keyshift_change(deck, -1);
    } else if (part == 1u) {
        /* One control, and the label says which of the two it will do: take
           the deck into key with the other one, or put it back where it
           started once there is nothing left to match. */
        int match = keyshift_match_delta(deck);
        rx3_keyshift_change(deck, match ? match : -rx3_keyshift_semitones(deck));
    } else {
        rx3_keyshift_change(deck, 1);
    }
}

/* One stepper across the deck's half. It used to be three controls whose
   coordinates were written out by hand, and the last of them was twenty pixels
   wider than the other two for no reason anyone recorded. */
static const struct rx3_pad_widget keyshift_widgets[1] = {
    { RX3_PAD_STEPPER, 1 }
};

static const struct rx3_pad_row keyshift_row = {
    1u, TAB_IMAGE_KEY, RX3_PAD_SCOPE_DECK, 1u, keyshift_widgets,
    0, keyshift_caption, keyshift_is_on, keyshift_fire,
    0, 0, 0, 0
};

#endif /* RX3_KEYSHIFT_PANEL_H */
