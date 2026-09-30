/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_SAMPLES_PANEL_H
#define RX3_SAMPLES_PANEL_H

static const uint16_t *samples_caption(unsigned int deck, unsigned int widget,
                                       unsigned int part)
{
    (void)deck;
    (void)part;
    static uint16_t label[8] = {'V','O','L',' ',0};
    static const uint16_t no_lettering[] = {0};
    if (widget == 0u)
        return no_lettering;            /* the track carries no lettering */
    unsigned int volume = __atomic_load_n(&samples_volume, __ATOMIC_SEQ_CST);
    if (volume >= 100u) {
        label[4] = '1'; label[5] = '0'; label[6] = '0'; label[7] = 0;
    } else {
        label[4] = (uint16_t)('0' + volume / 10u);
        label[5] = (uint16_t)('0' + volume % 10u);
        label[6] = 0;
    }
    return label;
}

static int samples_is_on(unsigned int deck, unsigned int widget,
                         unsigned int part)
{
    (void)deck; (void)widget; (void)part;
    return 0;
}

/* Tapping the readout puts the level back to what the bank was saved with,
   which is the only way back once a set has moved it. */
static void samples_fire(unsigned int deck, unsigned int widget,
                         unsigned int part)
{
    (void)deck; (void)part;
    if (widget != 1u) return;
    unsigned int volume = __atomic_load_n(&samples_config.volume, __ATOMIC_SEQ_CST);
    if (volume > 100u) volume = 100u;
    __atomic_store_n(&samples_volume_touched, 1u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&samples_volume, volume, __ATOMIC_SEQ_CST);
}

static unsigned int samples_slider_max(unsigned int deck, unsigned int widget)
{
    (void)deck; (void)widget;
    return 100u;
}

static unsigned int samples_slider_get(unsigned int deck, unsigned int widget)
{
    (void)deck; (void)widget;
    unsigned int volume = __atomic_load_n(&samples_volume, __ATOMIC_SEQ_CST);
    return volume > 100u ? 100u : volume;
}

static void samples_slider_set(unsigned int deck, unsigned int widget,
                               unsigned int value, unsigned int committed)
{
    (void)deck; (void)widget;
    if (value > 100u) value = 100u;
    __atomic_store_n(&samples_volume_touched, 1u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&samples_volume, value, __ATOMIC_SEQ_CST);
    /* One line when the finger leaves, not one per report: this runs from the
       input path and the drive is the thing being written to. */
    if (committed)
        log_number("sample volume = ", value);
}

static int samples_panel_needs_refresh(void)
{
    static unsigned int seen = SAMPLE_SLOT_IDLE;
    unsigned int volume = __atomic_load_n(&samples_volume, __ATOMIC_SEQ_CST);
    int changed = seen != volume;
    seen = volume;
    return changed;
}

/* The level is one control across the whole screen rather than one per deck:
   there is one bank and one volume, so splitting it in two would have said
   there were two. The readout sits at the end of it. */
static const struct rx3_pad_widget samples_widgets[2] = {
    { RX3_PAD_SLIDER, 9 }, { RX3_PAD_BUTTON, 1 }
};

static void samples_activate(unsigned int active);

/* Panel 3 is the status slot: it replaces the native STATUS tab. */
static const struct rx3_pad_row samples_row = {
    .panel_id = 3u, .tab_image = 0u, .scope = RX3_PAD_SCOPE_SCREEN,
    .count = 2u, .widgets = samples_widgets,
    .caption = samples_caption, .is_on = samples_is_on, .fire = samples_fire,
    .slider_max = samples_slider_max, .slider_get = samples_slider_get,
    .slider_set = samples_slider_set, .needs_refresh = samples_panel_needs_refresh,
    .activate = samples_activate
};

#endif /* RX3_SAMPLES_PANEL_H */
