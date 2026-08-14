/* SPDX-License-Identifier: MPL-2.0
 * Stems implementation of the core feature-panel contract.
 */

#ifndef RX3_STEMS_PANEL_H
#define RX3_STEMS_PANEL_H

static const uint16_t stems_text_instrumental[] = {
    'I','N','S','T','R','U','M','E','N','T','A','L',0
};
static const uint16_t stems_text_vocal[] = {'V','O','C','A','L',0};

static const uint16_t *stems_panel_label(unsigned int deck,
                                         unsigned int control)
{
    (void)deck;
    return control == 0u ? stems_text_instrumental : stems_text_vocal;
}

static int stems_panel_selected(unsigned int deck, unsigned int control)
{
    if (deck_is_loading(&stems_decks[deck]))
        return blink_phase_is_on();
    int armed = stems_decks[deck].reader && stems_decks[deck].armed;
    enum stem_mode bit = control == 0u ? MODE_INSTRUMENTAL : MODE_VOCAL;
    return armed && (stems_decks[deck].mode & bit);
}

static void stems_panel_activate(unsigned int deck, unsigned int control)
{
    enum stem_mode bit = control == 0u ? MODE_INSTRUMENTAL : MODE_VOCAL;
    if (stems_decks[deck].reader && stems_decks[deck].armed)
        stems_decks[deck].mode =
            (enum stem_mode)(stems_decks[deck].mode ^ bit);
}

static int stems_panel_needs_refresh(void)
{
    return any_deck_is_loading();
}

static const int stems_panel_lefts[2] = {19, 326};
static const int stems_panel_rights[2] = {306, 613};

static const struct rx3_panel_feature stems_panel = {
    2u, TAB_IMAGE_STEMS, 2u, stems_panel_lefts, stems_panel_rights,
    stems_panel_label, stems_panel_selected, stems_panel_activate,
    stems_panel_needs_refresh
};

#endif /* RX3_STEMS_PANEL_H */
