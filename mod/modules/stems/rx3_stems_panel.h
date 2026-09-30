/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_PANEL_H
#define RX3_STEMS_PANEL_H

#include "rx3_stems_audio.h"

static const uint16_t stems_text_instrumental[] = {'I','N','S','T','R','U','M','E','N','T','A','L',0};
static const uint16_t stems_text_inst[] = {'I','N','S','T',0};
static const uint16_t stems_text_vocal[] = {'V','O','C','A','L',0};
static const uint16_t stems_text_drums[] = {'D','R','U','M','S',0};
static const uint16_t stems_text_none[] = {'N','O',' ','S','T','E','M','S',0};
static const uint16_t stems_text_failed[] = {'S','T','E','M','S',' ','E','R','R',0};
/* Last committed full-volume adjustment, in the core's millisecond clock. */
static unsigned int stems_slider_until[2][4];

/* SLIP LOOP pads 5 to 8 and the touch controls, left to right: INST, VOCAL,
   DRUMS. Pad 8 has no role and keeps its native loop. A legacy bass payload
   has no bit here: it plays at the INST level. */
static const unsigned int stems_display_order[4] = {1u,2u,4u,0u};
struct stems_rgb { uint8_t red, green, blue; };
static const struct stems_rgb stems_pad_colour[4] = {
    {255u,0u,0u}, {0u,255u,0u}, {120u,200u,255u}, {0u,0u,0u}
};

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
    unsigned int selected = stems_selected(context);
    if (!context->payloads[0].data) {
#ifdef RX3_OVERCUE_PROTOTYPE
        if(!context->overcue)
#endif
        return blink_phase_is_on();
    }
    return (selected & stems_control_bit(available, widget)) != 0u;
}

static void stems_fire(unsigned int deck, unsigned int widget, unsigned int part)
{
    (void)part;
    struct stems_deck_context *context = &stems_decks[deck];
    if (__atomic_load_n(&context->status, __ATOMIC_SEQ_CST) != 2u ||
        !context->reader || !context->armed) return;
    __atomic_store_n(&stems_slider_until[deck][widget], 0u, __ATOMIC_SEQ_CST);
    stems_toggle(context, stems_control_bit(stems_available(context), widget));
}

static int stems_slider_visible(unsigned int deck, unsigned int widget)
{
    struct stems_deck_context *context = &stems_decks[deck];
    if (context->status != 2u) return 0;
    unsigned int value = stems_level(context, stems_control_bit(stems_available(context), widget));
    unsigned int until = __atomic_load_n(&stems_slider_until[deck][widget], __ATOMIC_SEQ_CST);
    return value && (value < 100u || (until && (int)(until - now_ms()) > 0));
}

/* Watcher thread. While a deck loads, the row is redrawn on each blink phase
   change and nothing else, so the toggles keep the LEDs' parity; the pending
   changes land with the next phase. */
static int stems_panel_needs_refresh(void)
{
    static unsigned int seen[2][4];
    static int last_phase = -1;
    int changed = 0;
    for (unsigned int deck = 0; deck < 2u; deck++) {
#ifdef RX3_OVERCUE_PROTOTYPE
        if(stems_decks[deck].overcue)
            __atomic_store_n(&stems_decks[deck].status,rx3_overcue_status(deck),__ATOMIC_SEQ_CST);
#endif
        unsigned int status = __atomic_load_n(&stems_decks[deck].status, __ATOMIC_SEQ_CST);
        unsigned int selection = __atomic_load_n(&stems_decks[deck].selection, __ATOMIC_SEQ_CST);
        unsigned int levels = __atomic_load_n(&stems_decks[deck].levels, __ATOMIC_SEQ_CST);
        unsigned int mode = 0u;
        for (unsigned int w = 0; w < 4u; w++)
            if (stems_slider_visible(deck, w)) mode |= 1u << w;
        if (seen[deck][2] != levels || seen[deck][3] != mode) changed = 1;
        seen[deck][2] = levels; seen[deck][3] = mode;
        if (seen[deck][0] != status || seen[deck][1] != selection) changed = 1;
        seen[deck][0] = status; seen[deck][1] = selection;
    }
    if (stems_any_deck_loading()) {
        int phase = blink_phase_is_on();
        changed = phase != last_phase;
        last_phase = phase;
    } else {
        last_phase = -1;
        if (!changed) stems_blink_idle();
    }
    return changed;
}

static unsigned int stems_widget_kind(unsigned int deck, unsigned int widget)
{
    (void)widget;
#ifdef RX3_OVERCUE_PROTOTYPE
    if(stems_decks[deck].overcue)return RX3_PAD_BUTTON;
#endif
    return stems_decks[deck].status == 2u ? RX3_PAD_TOGGLE_SLIDER : RX3_PAD_BUTTON;
}
static uint16_t stems_widget_colour(unsigned int deck, unsigned int widget)
{
    switch(stems_control_bit(stems_available(&stems_decks[deck]),widget)) {
    case 4u: return 0x001fu;
    case 1u: return 0xf800u;
    case 2u: return 0x07e0u;
    default: return 0x8410u;
    }
}
static unsigned int stems_slider_max(unsigned int deck, unsigned int widget)
{
    (void)deck; (void)widget; return 100u;
}
static unsigned int stems_slider_get(unsigned int deck, unsigned int widget)
{
    struct stems_deck_context *context=&stems_decks[deck];
    return stems_level(context,stems_control_bit(stems_available(context),widget));
}
static void stems_slider_set(unsigned int deck, unsigned int widget,
                             unsigned int value, unsigned int committed)
{
    struct stems_deck_context *context=&stems_decks[deck];
    if(context->status!=2u || !context->reader || !context->armed) return;
    stems_set_level(context,stems_control_bit(stems_available(context),widget),value);
    __atomic_store_n(&stems_slider_until[deck][widget],
                     committed && value >= 100u ? now_ms() + 2000u : 0u, __ATOMIC_SEQ_CST);
}
static const struct rx3_pad_widget stems_widgets[4] = {
    {RX3_PAD_TOGGLE_SLIDER,1}, {RX3_PAD_TOGGLE_SLIDER,1},
    {RX3_PAD_TOGGLE_SLIDER,1}, {RX3_PAD_TOGGLE_SLIDER,1}
};
static const struct rx3_pad_row stems_row = {
    .panel_id=2u, .tab_image=TAB_IMAGE_STEMS, .scope=RX3_PAD_SCOPE_DECK,
    .count=4u, .widgets=stems_widgets, .live_count=stems_live_count,
    .caption=stems_caption, .is_on=stems_is_on, .fire=stems_fire,
    .slider_max=stems_slider_max, .slider_get=stems_slider_get, .slider_set=stems_slider_set,
    .needs_refresh=stems_panel_needs_refresh, .kind=stems_widget_kind, .colour=stems_widget_colour,
    .slider_visible=stems_slider_visible
};
#endif /* RX3_STEMS_PANEL_H */
