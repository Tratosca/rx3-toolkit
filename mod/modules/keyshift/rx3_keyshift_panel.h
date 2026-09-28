/* SPDX-License-Identifier: MPL-2.0
 * Key Shift implementation of the core feature-panel contract.
 */

#ifndef RX3_KEYSHIFT_PANEL_H
#define RX3_KEYSHIFT_PANEL_H

#include "rx3_keyshift_text.h"

static int keyshift_track_key[2] = {-1, -1};
static unsigned keyshift_metadata_active;
static uint16_t keyshift_labels[2][3][12];
static int keyshift_base_key(unsigned deck)
{
    return deck<2?__atomic_load_n(&keyshift_track_key[deck],__ATOMIC_SEQ_CST):-1;
}

/* Where a deck sits on the wheel right now, shift included. */
static int keyshift_current_key(unsigned int deck)
{
    if (deck >= 2u) return -1;
    return rx3_camelot_shifted(keyshift_base_key(deck),
                               rx3_keyshift_semitones(deck));
}

static struct rx3_harmonic_reference keyshift_reference(unsigned deck)
{
    struct rx3_harmonic_reference ref={-1,-1,0};
    if(deck>1 || !framework->browse || !framework->browse->reference)return ref;
    ref=framework->browse->reference();
    if(ref.deck==(int)deck)ref.key=-1;
    return ref;
}
static int keyshift_sync_compatible(unsigned int deck)
{
    struct rx3_harmonic_reference ref=keyshift_reference(deck);
    return keyshift_sync_enabled && deck<2 && keyshift_sync_harmonic &&
        rx3_harmonic_accepts(ref.key,keyshift_current_key(deck),ref.native_keys,keyshift_match_rules);
}
static int keyshift_match_delta(unsigned int deck)
{
    struct rx3_harmonic_reference ref=keyshift_reference(deck);
    if(!keyshift_sync_enabled || deck>1)return 0;
    return rx3_harmonic_delta(keyshift_base_key(deck),rx3_keyshift_semitones(deck),
        ref.key,ref.native_keys,keyshift_match_rules,keyshift_sync_range,keyshift_sync_harmonic);
}

static unsigned int keyshift_live_count(unsigned int deck)
{
    /* Only the other deck needs a match/sync slot; MASTER keeps its key stepper. */
    return keyshift_sync_enabled && keyshift_current_key(deck)>=0 &&
        keyshift_current_key(deck^1u)>=0 && keyshift_reference(deck).deck!=(int)deck ? 2u : 1u;
}

static unsigned int keyshift_widget_kind(unsigned int deck, unsigned int widget)
{
    return widget == 0u ? RX3_PAD_STEPPER :
        keyshift_match_delta(deck) ? RX3_PAD_OUTLINE_BUTTON : RX3_PAD_STATUS;
}

/* The three strings the row shows are indexed the way the stepper's parts are:
   decrement, value, increment. keyshift_format_labels already writes them in
   that order, so nothing here has to be rearranged. */
static const uint16_t *keyshift_caption(unsigned int deck, unsigned int widget,
                                        unsigned int part)
{
    if (deck >= 2u || part >= 3u) return keyshift_labels[0][1];
    if (widget == 1u) {
        static const uint16_t empty[]={0};
        if(keyshift_reference(deck).deck==(int)deck)return empty;
        static const uint16_t compatible[]={'K','E','Y',' ','M','A','T','C','H',0};
        static const uint16_t identical[]={'I','D','E','N','T','I','Q','U','E',0};
        static const uint16_t unavailable[]={'P','A','S',' ','D','E',' ','S','Y','N','C',0};
        if (keyshift_sync_compatible(deck)) return compatible;
        if (!keyshift_match_delta(deck)) return keyshift_current_key(deck)>=0 &&
            keyshift_current_key(deck)==keyshift_reference(deck).key ? identical : unavailable;
        static uint16_t sync_labels[2][16];
        static const uint16_t prefix[]={'K','E','Y',' ','S','Y','N','C',' ',0};
        memcpy(sync_labels[deck],prefix,9u*sizeof(uint16_t));
        uint16_t *end=keyshift_put_signed(sync_labels[deck]+9,keyshift_match_delta(deck));
        *end=0;
        return sync_labels[deck];
    }
    keyshift_format_labels(keyshift_labels[deck], keyshift_base_key(deck),
                           rx3_keyshift_semitones(deck));
    return keyshift_labels[deck][part];
}

/* Current-key face and small target-colour hints for the manual step actions. */
static uint16_t keyshift_part_colour(unsigned int deck, unsigned int widget,
                                     unsigned int part)
{
    if (deck >= 2u || part >= 3u) return 0u;
    if (widget == 1u) {
        int delta=keyshift_match_delta(deck);
        return delta ? rx3_camelot_colour(
            rx3_camelot_shifted(keyshift_base_key(deck),rx3_keyshift_semitones(deck)+delta)) : 0u;
    }
    int shift = rx3_keyshift_semitones(deck);
    if ((part == 0u && shift <= -12) || (part == 2u && shift >= 12)) return 0u;
    int delta = part == 0u ? -1 : part == 2u ? 1 : 0;
    return rx3_camelot_colour(rx3_camelot_shifted(keyshift_base_key(deck),shift+delta));
}

static unsigned int keyshift_refresh_pending;
static void keyshift_publish_key(unsigned deck,int key)
{
    if(deck>1)return;
    __atomic_store_n(&keyshift_track_key[deck],key,__ATOMIC_SEQ_CST);
    if(framework->browse && framework->browse->deck_key)
        framework->browse->deck_key(deck,key,rx3_keyshift_semitones(deck));
    __atomic_store_n(&keyshift_refresh_pending,1u,__ATOMIC_SEQ_CST);
}
static int keyshift_needs_refresh(void)
{
    static struct rx3_harmonic_reference previous={-1,-1,0};
    struct rx3_harmonic_reference current={-1,-1,0};
    if(framework->browse && framework->browse->reference)current=framework->browse->reference();
    int changed=current.deck!=previous.deck || current.key!=previous.key || current.native_keys!=previous.native_keys;
    previous=current;
    return (__atomic_exchange_n(&keyshift_refresh_pending, 0u, __ATOMIC_SEQ_CST) != 0u) || changed;
}
static void keyshift_capture_text(const struct rx3_text_observation *observation)
{
    if(keyshift_metadata_active)return;
    const uint16_t *box=observation->box;
    int deck=keyshift_text_deck(observation->layer,box[0],box[1],box[2],box[3]);
    if (deck<0) return;
    int key=keyshift_key_from_glyph_text(observation->text,observation->length);
    if (key==keyshift_base_key(deck)) return;
    keyshift_publish_key((unsigned)deck,key);
}

/* Lit when the two decks mix, so being in key is something a DJ glances at
   rather than works out. With only one key on screen there is nothing to be in
   key with, and the value falls back to marking an unshifted deck. */
static int keyshift_is_on(unsigned int deck, unsigned int widget,
                          unsigned int part)
{
    if (widget == 1u) return keyshift_sync_compatible(deck) || keyshift_match_delta(deck) != 0;
    if (part != 1u) return 0;
    int here = keyshift_current_key(deck);
    int theirs = keyshift_current_key(deck ^ 1u);
    if (here < 0) return 0;
    if (theirs >= 0)
        return keyshift_sync_compatible(deck) || (keyshift_reference(deck).key==here);
    return rx3_keyshift_semitones(deck) == 0;
}

static void keyshift_fire(unsigned int deck, unsigned int widget,
                          unsigned int part)
{
    if (deck >= 2u) return;
    if (widget == 1u) {
        /* Re-evaluate on release: the other deck may have changed while held. */
        int delta=keyshift_match_delta(deck);
        if (delta) rx3_keyshift_change(deck,delta);
    } else if (part == 0u) {
        rx3_keyshift_change(deck,-1);
    } else if (part == 1u) {
        rx3_keyshift_change(deck,-rx3_keyshift_semitones(deck));
    } else {
        rx3_keyshift_change(deck,1);
    }
    if(framework->browse && framework->browse->deck_key)
        framework->browse->deck_key(deck,keyshift_base_key(deck),rx3_keyshift_semitones(deck));
}

/* Separate sync action; harmonic mode retains an inert compatibility status. */
static const struct rx3_pad_widget keyshift_widgets[2] = {
    {RX3_PAD_STEPPER,2}, {RX3_PAD_BUTTON,1}
};
static const struct rx3_pad_row keyshift_row = {
    .panel_id=1u, .tab_image=TAB_IMAGE_KEY, .scope=RX3_PAD_SCOPE_DECK,
    .count=2u, .widgets=keyshift_widgets, .live_count=keyshift_live_count,
    .caption=keyshift_caption, .is_on=keyshift_is_on, .fire=keyshift_fire,
    .needs_refresh=keyshift_needs_refresh, .part_colour=keyshift_part_colour, .kind=keyshift_widget_kind
};

#endif /* RX3_KEYSHIFT_PANEL_H */
