/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMWAVE_FEATURE_H
#define RX3_STEMWAVE_FEATURE_H

#include "rx3_stemwave_render.h"

static int stemwave_enabled;
static struct stemwave_deck stemwave_decks[2];
static unsigned int stemwave_reported_shapes;
static unsigned int stemwave_package_reported;
static unsigned int stemwave_axis_reported;

/* Availability and selected roles are published together by the stems loader. */
static struct stemwave_selection stemwave_selection_for(unsigned int deck)
{
    struct rx3_mix_state state = framework->mix_state(deck);
    struct stemwave_selection selection = {
        .selected = state.ready ? state.selected : state.available,
        .available = state.available
    };
    return selection;
}

static int hooked_ex_wave_renew_check(unsigned int deck)
{
    int result = original_ex_wave_renew_check(deck);
    if (deck >= 2u)
        return result;
    struct stemwave_deck *state = &stemwave_decks[deck];
    const uint8_t *player = (const uint8_t *)(WAVEFORM_STATE_BASE + deck * WAVEFORM_STATE_STRIDE);
    unsigned int shape = *(const uint32_t *)(player + WAVEFORM_MODE_OFFSET);
    struct stemwave_selection selection = stemwave_selection_for(deck);
    /* Probe before overview or column writes; absence is not a render hint. */
    if (framework->waveform(deck, 0u, shape==WAVEFORM_3BAND?3u:shape, state->package_amplitudes, 0u) == 0xfffffffeu)
        return result;
    if (shape == WAVEFORM_3BAND)
        stemwave_blue_overview(state, (uint8_t *)(WAVEFORM_3BAND_BASE + deck * WAVEFORM_3BAND_BYTES), selection);

    enum stemwave_action action = stemwave_renew_action(state, result, selection.selected | (shape << 8u));
    if (action == STEMWAVE_REQUEST) {
        ((void (*)(unsigned int, unsigned int))WAVEFORM_REQUEST_RENEW)(deck, 1u);
        return result;
    }
    if (action != STEMWAVE_PAINT || selection.selected == selection.available)
        return result;
    struct stemwave_style style = {.colour = 0xffffu, .roles = 7u, .suppress_high = 0};
    int supported = stemwave_style_for(selection, &style);
    unsigned int offset = shape == WAVEFORM_RGB ? WAVEFORM_COUNT_BANDS :
        (shape == WAVEFORM_3BAND ? WAVEFORM_COUNT_BLUE : WAVEFORM_COUNT_FLAT);
    const uint32_t *count_pointer = *(const uint32_t *const *)(player + offset);
    if (!count_pointer)
        return result;
    unsigned int count = *count_pointer;
    if (count > WAVEFORM_COLUMN_LIMIT)
        count = WAVEFORM_COLUMN_LIMIT;
    if (!count || shape > WAVEFORM_3BAND)
        return result;
    struct waveform_column *columns = (struct waveform_column *)(WAVEFORM_COLUMNS_BASE + deck * WAVEFORM_COLUMN_STRIDE);
    unsigned int embedded = framework->waveform(deck, selection.selected, shape==WAVEFORM_3BAND?3u:shape, state->package_amplitudes, count);
    if (embedded == 0xfffffffeu) return result;
    if (embedded == 0xffffffffu) {
        if (!stemwave_axis_reported) {
            stemwave_axis_reported=1u;
            framework->log_line("stem waveform: package axis mismatch, keeping native waveform");
        }
        return result;
    }
    if (embedded == count) {
        if(shape==WAVEFORM_3BAND)
            stemwave_decode_pwv7(columns, state->package_amplitudes, count);
        else
            stemwave_decode_columns(columns, state->package_amplitudes, count, shape);
        if (!stemwave_package_reported) {
            stemwave_package_reported=1u;
            framework->log_line("stem waveform: rendered embedded package waveform");
        }
    } else if (supported) {
        stemwave_render_columns(columns, count, shape, &style);
    } else {
        return result;
    }
    __atomic_store_n(&state->columns, count, __ATOMIC_SEQ_CST);
    if (!(stemwave_reported_shapes & (1u << shape))) {
        stemwave_reported_shapes |= 1u << shape;
        framework->log_line("stem waveform: rendered a new shape");
    }
    return result;
}

static int stemwave_feature_configured(void)
{
    const char *setting = getenv("RX3_STEMS_DIR");
    stemwave_enabled = setting && setting[0];
    return stemwave_enabled;
}

static int stemwave_feature_install(void)
{
    /* This direct call needs its own guard before any waveform writes.
       Hardware validation is pending. */
    const char *stems = getenv("RX3_STEMS_DIR");
    if (!stems || !stems[0]) {
        framework->log_line("stemwave refused: stems provider not configured");
        return 0;
    }
    static const uint8_t renew_guard[8] = {0x56, 0x0e, 0x80, 0xe2, 0x01, 0x20, 0x41, 0xe2};
    if (!stemwave_enabled || memcmp((const void *)WAVEFORM_REQUEST_RENEW, renew_guard, 8u))
        return 0;
    original_ex_wave_renew_check = (ex_wave_renew_check_fn)framework->install_hook(
        &ex_wave_renew_hook, EX_WAVE_RENEW_CHECK, ex_wave_renew_guard,
        hooked_ex_wave_renew_check);
    if (!original_ex_wave_renew_check)
        return 0;
    framework->log_line("stem waveform: refresh hook installed");
    return 1;
}

static void stemwave_feature_remove(void)
{
    if (framework->uninstall_hook(&ex_wave_renew_hook))
        original_ex_wave_renew_check = 0;
}

static void stemwave_feature_track_did_load(unsigned int deck, void *reader,
                                           const void *track_info)
{
    (void)reader;
    (void)track_info;
    if (deck >= 2u)
        return;
    struct stemwave_deck *state = &stemwave_decks[deck];
    __atomic_store_n(&state->drawn_mask, STEMWAVE_MASK_INITIAL, __ATOMIC_SEQ_CST);
    __atomic_store_n(&state->pending, 0u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&state->columns, 0u, __ATOMIC_SEQ_CST);
    __atomic_store_n(&state->blue_saved, 0u, __ATOMIC_SEQ_CST);
    __sync_synchronize();
}

#endif /* RX3_STEMWAVE_FEATURE_H */
