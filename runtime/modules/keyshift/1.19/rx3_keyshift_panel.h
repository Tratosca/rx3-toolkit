/* SPDX-License-Identifier: MPL-2.0
 * Key Shift implementation of the core feature-panel contract.
 */

#ifndef RX3_KEYSHIFT_PANEL_H
#define RX3_KEYSHIFT_PANEL_H

static const uint16_t keyshift_text_down[] = {'K','E','Y',' ','-',0};
static const uint16_t keyshift_text_up[] = {'K','E','Y',' ','+',0};

static const uint16_t *keyshift_panel_label(unsigned int deck,
                                            unsigned int control)
{
    if (control == 0u)
        return keyshift_text_down;
    if (control == 1u)
        return rx3_keyshift_label(deck);
    return keyshift_text_up;
}

static int keyshift_panel_selected(unsigned int deck, unsigned int control)
{
    return control == 1u && rx3_keyshift_semitones(deck) == 0;
}

static void keyshift_panel_activate(unsigned int deck, unsigned int control)
{
    if (control == 0u)
        rx3_keyshift_change(deck, -1);
    else if (control == 1u)
        rx3_keyshift_change(deck, -rx3_keyshift_semitones(deck));
    else
        rx3_keyshift_change(deck, 1);
}

static const int keyshift_panel_lefts[3] = {19, 215, 411};
static const int keyshift_panel_rights[3] = {201, 397, 613};

static const struct rx3_panel_feature keyshift_panel = {
    1u, TAB_IMAGE_KEY, 3u, keyshift_panel_lefts, keyshift_panel_rights,
    keyshift_panel_label, keyshift_panel_selected, keyshift_panel_activate, 0
};

#endif /* RX3_KEYSHIFT_PANEL_H */
