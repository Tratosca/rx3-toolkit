/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMWAVE_RENDER_H
#define RX3_STEMWAVE_RENDER_H

/* All non-vocal roles together use the instrumental colour, including 0xd
   on a four-stem track. Full mix and unsupported combinations stay stock. */
static int stemwave_style_for(struct stemwave_selection selection,
                              struct stemwave_style *style)
{
    unsigned int mask = selection.selected;
    if (mask == selection.available)
        return 0;
    style->suppress_high = 0;
    style->roles = 7u;
    if (mask == 0u || mask == 2u) {
        style->colour = mask ? STEMWAVE_COLOUR_TWO : STEMWAVE_COLOUR_NONE;
        style->roles = mask ? 1u : 0u;
        style->suppress_high = 1;
    } else if (mask == (selection.available & 0xdu)) {
        style->colour = STEMWAVE_COLOUR_ONE;
        style->roles = 6u;
    } else if (mask == 1u) {
        style->colour = STEMWAVE_COLOUR_ONE;
    } else if (mask == 4u) {
        style->colour = STEMWAVE_COLOUR_FOUR;
    } else if (mask == 8u) {
        style->colour = STEMWAVE_COLOUR_EIGHT;
    } else {
        return 0;
    }
    return 1;
}

enum stemwave_action { STEMWAVE_KEEP, STEMWAVE_REQUEST, STEMWAVE_PAINT };

/* A return of 1 starts a stock rebuild. Paint only on the first later check.
   A changed selection requests that cycle instead of editing old columns. */
static enum stemwave_action stemwave_renew_action(struct stemwave_deck *state,
                                                  int result,
                                                  unsigned int selected)
{
    if (result == 1) {
        __atomic_store_n(&state->pending, 1u, __ATOMIC_SEQ_CST);
        return STEMWAVE_KEEP;
    }
    if (__sync_bool_compare_and_swap(&state->pending, 1u, 0u)) {
        __atomic_store_n(&state->drawn_mask, selected, __ATOMIC_SEQ_CST);
        __atomic_store_n(&state->columns, 0u, __ATOMIC_SEQ_CST);
        return STEMWAVE_PAINT;
    }
    if (__sync_val_compare_and_swap(&state->drawn_mask, 0u, 0u) == selected)
        return STEMWAVE_KEEP;
    __atomic_store_n(&state->drawn_mask, selected, __ATOMIC_SEQ_CST);
    return STEMWAVE_REQUEST;
}

/* Keep the stock Blue overview so returning to full mix restores hidden
   bands. A table changed by the player becomes the new source snapshot. */
static void stemwave_blue_overview(struct stemwave_deck *state, uint8_t *table,
                                   struct stemwave_selection selection)
{
    struct stemwave_style style;
    int supported = selection.selected != selection.available &&
        (selection.selected == 0u || selection.selected == 2u ||
         selection.selected == (selection.available & 0xdu));
    if (!supported) {
        if (__sync_val_compare_and_swap(&state->blue_saved, 0u, 0u)) {
            memcpy(table, state->blue_original, WAVEFORM_3BAND_BYTES);
            __atomic_store_n(&state->blue_saved, 0u, __ATOMIC_SEQ_CST);
        }
        return;
    }
    (void)stemwave_style_for(selection, &style);
    if (!__sync_val_compare_and_swap(&state->blue_saved, 0u, 0u) ||
        memcmp(table, state->blue_filtered, WAVEFORM_3BAND_BYTES)) {
        memcpy(state->blue_original, table, WAVEFORM_3BAND_BYTES);
        __atomic_store_n(&state->blue_saved, 1u, __ATOMIC_SEQ_CST);
    }
    for (unsigned int i = 0; i < WAVEFORM_3BAND_BYTES; i += 3u) {
        state->blue_filtered[i] = style.suppress_high ? 0u : state->blue_original[i];
        state->blue_filtered[i + 1u] = (style.roles & 2u) ? state->blue_original[i + 1u] : 0u;
        state->blue_filtered[i + 2u] = (style.roles & 1u) ? state->blue_original[i + 2u] : 0u;
    }
    memcpy(table, state->blue_filtered, WAVEFORM_3BAND_BYTES);
}

static unsigned int stemwave_blue_role(unsigned int rgb)
{
    unsigned int red = (rgb >> 8u) & 0xf8u;
    unsigned int green = (rgb >> 3u) & 0xfcu;
    unsigned int blue = (rgb << 3u) & 0xffu;
    if (!(red | green | blue))
        return 0u;
    unsigned int low = red < green ? red : green;
    unsigned int high = red > green ? red : green;
    if (blue < low)
        low = blue;
    if (blue > high)
        high = blue;
    return high - low < 0x28u ? 1u : (blue > red ? 4u : 2u);
}

static void stemwave_render_columns(struct waveform_column *columns,
                                    unsigned int count, unsigned int shape,
                                    const struct stemwave_style *style)
{
    for (unsigned int i = 0; i < count; i++) {
        struct waveform_column *column = &columns[i];
        if (shape == WAVEFORM_BLUE) {
            column->colour[0] = style->colour;
        } else if (shape == WAVEFORM_RGB) {
            unsigned int packed = column->colour[0];
            unsigned int high = (packed >> 13u) & 7u;
            unsigned int middle = (packed >> 8u) & 7u;
            unsigned int low = (packed >> 2u) & 7u;
            unsigned int sum = high + middle + low;
            if (!sum)
                continue;
            unsigned int kept = style->suppress_high ? 0u : high;
            if (style->roles & 2u)
                kept += middle;
            if (style->roles & 1u)
                kept += low;
            column->colour[0] = style->colour;
            column->amplitude[0] = (uint8_t)((kept * column->amplitude[0] + sum / 2u) / sum);
        } else if (shape == WAVEFORM_3BAND) {
            for (unsigned int band = 0; band < 3u; band++) {
                uint32_t value = column->colour[band];
                /* The field can be a palette pointer. Its range is 32 bytes. */
                unsigned int rgb = value - WAVEFORM_PALETTE_BASE < WAVEFORM_PALETTE_BYTES
                    ? *(const uint16_t *)(unsigned long)value : value & 0xffffu;
                unsigned int role = stemwave_blue_role(rgb);
                if (!role)
                    continue;
                if (role & style->roles)
                    column->colour[band] = style->colour;
                else
                    column->amplitude[band] = 0u;
            }
        }
    }
}


/* Decode precomputed columns using native display semantics, not stem colours.
   Native modes verified in rbp: Blue=0, RGB=1, 3Band=2. */
static void stemwave_decode_columns(struct waveform_column *columns,
                                    const uint8_t *data, unsigned int count,
                                    unsigned int shape)
{
    static const uint16_t blue[8]={0x09f1u,0x0af7u,0x037fu,0x0d5eu,0x55beu,0x757fu,0x757fu,0xcf3fu};
    static const uint16_t bands[3]={0x02bcu,0xfd20u,0xffffu};
    for(unsigned int i=0;i<count;i++) {
        struct waveform_column *c=&columns[i];
        memset(c,0,sizeof(*c));
        if(shape==WAVEFORM_BLUE) {
            c->amplitude[0]=data[i]&31u;
            c->colour[0]=blue[data[i]>>5u];
        } else if(shape==WAVEFORM_RGB) {
            unsigned int value=((unsigned int)data[i*2u]<<8u)|data[i*2u+1u];
            c->amplitude[0]=(value>>2u)&31u;
            c->colour[0]=(value&0xe000u)|((value&0x1c00u)>>2u)|((value&0x0380u)>>5u);
        } else {
            for(unsigned int band=0;band<3u;band++) {
                c->amplitude[band]=data[i*3u+band];
                c->colour[band]=bands[band];
            }
        }
    }
}

/* PWV7 carries overlapping envelopes, not three stacked band heights.
   Split their union at each envelope boundary, using the native mixed colours.
   Palette: bit 0 high, bit 1 mid, bit 2 low. No audio filtering in the UI. */
static void stemwave_decode_pwv7(struct waveform_column *columns,
                                 const uint8_t *data, unsigned int count)
{
    static const uint32_t palette[8]={0,0xffff,0xfd20,0xff9a,0x02bc,0xd6ff,0xb341,0xf75a};
    for(unsigned int i=0;i<count;i++) {
        struct waveform_column *c=&columns[i];
        unsigned int heights[3]={data[i*3u+2u],data[i*3u+1u],data[i*3u]};
        unsigned int previous=0;
        memset(c,0,sizeof(*c));
        for(unsigned int layer=0;layer<3u;layer++) {
            unsigned int mask=0, next=256u;
            for(unsigned int b=0;b<3u;b++) {
                if(heights[b]>previous) {
                    mask|=1u<<b;
                    if(heights[b]<next) next=heights[b];
                }
            }
            if(!mask) break;
            c->amplitude[layer]=(uint8_t)(next-previous);
            c->colour[layer]=palette[mask];
            previous=next;
        }
    }
}

#endif /* RX3_STEMWAVE_RENDER_H */
