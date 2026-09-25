/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_PANEL_H
#define RX3_STEMS_PANEL_H

#include "rx3_stems_audio.h"

static const uint16_t stems_text_instrumental[] = {'I','N','S','T','R','U','M','E','N','T','A','L',0};
static const uint16_t stems_text_inst[] = {'I','N','S','T',0};
static const uint16_t stems_text_vocal[] = {'V','O','C','A','L',0};
static const uint16_t stems_text_drums[] = {'D','R','U','M','S',0};
static const uint16_t stems_text_bass[] = {'B','A','S','S',0};
static const uint16_t stems_text_none[] = {'N','O',' ','S','T','E','M','S',0};
static const uint16_t stems_text_failed[] = {'S','T','E','M','S',' ','E','R','R',0};
static const unsigned int stems_display_order[4] = {4u,8u,1u,2u};

static unsigned int stems_control_count(unsigned int available)
{
    unsigned int count = 0u;
    for (unsigned int i = 0; i < 4u; i++) if (available & (1u << i)) count++;
    return count < 2u ? 2u : count;
}

static unsigned int stems_control_bit(unsigned int available, unsigned int control)
{
    for (unsigned int i = 0; i < 4u; i++)
        if (available & stems_display_order[i]) {
            if (!control) return stems_display_order[i];
            control--;
        }
    return 0u;
}

/* How many controls this deck is showing. A deck with nothing loaded shows one,
   which carries the reason rather than a stem name. */
static unsigned int stems_live_count(unsigned int deck)
{
    struct stems_deck_context *context = &stems_decks[deck];
    unsigned int status = __atomic_load_n(&context->status, __ATOMIC_SEQ_CST);
    if (status != 1u && status != 2u) return 1u;
    return stems_control_count(stems_available(context));
}

static const uint16_t *stems_caption(unsigned int deck, unsigned int widget,
                                     unsigned int part)
{
    (void)part;
    struct stems_deck_context *context = &stems_decks[deck];
    unsigned int status = __atomic_load_n(&context->status, __ATOMIC_SEQ_CST);
    if (status != 1u && status != 2u)
        return status == 3u ? stems_text_failed : stems_text_none;
    unsigned int available = stems_available(context);
    switch (stems_control_bit(available, widget)) {
    case 4u: return stems_text_drums;
    case 8u: return stems_text_bass;
    case 2u: return stems_text_vocal;
    /* The long name only when there is room for it. */
    default: return stems_control_count(available) > 2u ? stems_text_inst
                                                        : stems_text_instrumental;
    }
}

/* Lit while the stem is playing, and blinking while the file is still being
   read, which is the only sign a deck gives that a load is under way. */
static int stems_is_on(unsigned int deck, unsigned int widget, unsigned int part)
{
    (void)part;
    struct stems_deck_context *context = &stems_decks[deck];
    unsigned int status = __atomic_load_n(&context->status, __ATOMIC_SEQ_CST);
    if (status != 1u && status != 2u) return 0;
    if (!context->reader || !context->armed) return 0;
    unsigned int available = stems_available(context);
    unsigned int selected = __atomic_load_n(&context->selection, __ATOMIC_SEQ_CST) & 15u;
    if (!context->payloads[0].data) return blink_phase_is_on();
    return (selected & stems_control_bit(available, widget)) != 0u;
}

static void stems_fire(unsigned int deck, unsigned int widget, unsigned int part)
{
    (void)part;
    struct stems_deck_context *context = &stems_decks[deck];
    if (__atomic_load_n(&context->status, __ATOMIC_SEQ_CST) != 2u ||
        !context->reader || !context->armed) return;
    stems_toggle(context, stems_control_bit(stems_available(context), widget));
}

static int stems_panel_needs_refresh(void)
{
    static unsigned int seen[2][2];
    int changed = 0;
    for (unsigned int deck = 0; deck < 2u; deck++) {
        unsigned int status = __atomic_load_n(&stems_decks[deck].status, __ATOMIC_SEQ_CST);
        unsigned int selection = __atomic_load_n(&stems_decks[deck].selection, __ATOMIC_SEQ_CST);
        if (seen[deck][0] != status || seen[deck][1] != selection || status == 1u) changed = 1;
        seen[deck][0] = status; seen[deck][1] = selection;
    }
    return changed;
}

/* Four toggles declared, as many drawn as the track actually carries. The strip
   used to lay itself out from a table of widths and gaps per count, and then
   work out what a finger had hit by repeating the same arithmetic. */
static const struct rx3_pad_widget stems_widgets[4] = {
    { RX3_PAD_TOGGLE, 1 }, { RX3_PAD_TOGGLE, 1 },
    { RX3_PAD_TOGGLE, 1 }, { RX3_PAD_TOGGLE, 1 }
};

static const struct rx3_pad_row stems_row = {
    2u, TAB_IMAGE_STEMS, RX3_PAD_SCOPE_DECK, 4u, stems_widgets,
    stems_live_count, stems_caption, stems_is_on, stems_fire,
    0, 0, 0, stems_panel_needs_refresh
};

#endif /* RX3_STEMS_PANEL_H */
