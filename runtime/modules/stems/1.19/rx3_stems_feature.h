/* SPDX-License-Identifier: MPL-2.0
 * Stems implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_STEMS_FEATURE_H
#define RX3_STEMS_FEATURE_H

static unsigned long hooked_get_stream(void *reader, unsigned long position,
                                       Float2 *output, unsigned long frames)
{
    unsigned long result = original_get_stream(reader, position, output, frames);
    struct stems_deck_context *context = context_for_reader(reader);
    if (!context)
        return result;
    int silent = block_is_silent(output, frames);
    if (!silent && context->vocal.data &&
        (uint64_t)position + frames <= context->vocal.frames) {
        enum stem_mode selected = context->mode;
        if (selected != MODE_BOTH ||
            context->transition_cursor < TRANSITION_FRAMES ||
            context->rendered_mode != MODE_BOTH)
            apply_mix(context, position, output, frames, selected);
    }
    return result;
}

static int hooked_on_key_pad(void *player_innards, const void *key_input)
{
    const uint8_t *event = key_input;
    uint16_t key_code = (uint16_t)event[8] | ((uint16_t)event[9] << 8);
    unsigned int operation = event[11] & 0x0fu;

    /* Pads 7 and 8 use key codes 0x411d and 0x411e. */
    if (key_code < 0x411du || key_code > 0x411eu)
        return original_on_key_pad(player_innards, key_input);

    unsigned int bit = 1u << (key_code - 0x411du);
    unsigned int object_channel =
        *(const uint8_t *)((const uint8_t *)player_innards + 0x26u);
    unsigned int event_channel = event[10];
    unsigned int ui_channel =
        event_channel >= 1u && event_channel <= 2u
        ? event_channel : object_channel;
    if (event_channel >= 1u && event_channel <= 2u &&
        object_channel != event_channel) {
        log_number("pad object/event channel mismatch, object = ",
                   object_channel);
        log_number("pad uses event channel = ", event_channel);
    }
    struct stems_deck_context *context =
        ui_channel >= 1u && ui_channel <= 2u
        ? &stems_decks[ui_channel - 1u] : 0;
    unsigned int deck = context
        ? (unsigned int)(context - stems_decks) : 0u;

    /* onKey_SlipBeatLoop writes 2 at PlayerInnards+0x74. onKey_Pad uses this
       value as its path selector. */
    int slip_loop =
        *(const uint32_t *)((const uint8_t *)player_innards + 0x74u) == 2u;

    if (operation == 0u && slip_loop && context && context->reader &&
        context->armed) {
        captured_pad_mask[deck] |= bit;
        enum stem_mode selected = context->mode;
        if (key_code == 0x411du)
            selected = (enum stem_mode)(selected ^ MODE_INSTRUMENTAL);
        else
            selected = (enum stem_mode)(selected ^ MODE_VOCAL);
        context->mode = selected;
        if (selected == MODE_VOCAL)
            log_line("SLIP LOOP PAD 8 : vocal");
        else if (selected == MODE_INSTRUMENTAL)
            log_line("SLIP LOOP PAD 7 : instrumental");
        else if (selected == MODE_NONE)
            log_line("SLIP LOOP : mute");
        else
            log_line("SLIP LOOP : both");
        return 1;
    }

    if (context && (captured_pad_mask[deck] & bit)) {
        if (operation == 2u || operation == 3u)
            captured_pad_mask[deck] &= ~bit;
        return 1;
    }
    return original_on_key_pad(player_innards, key_input);
}

struct stems_rgb { uint8_t red, green, blue; };

static void hooked_check_slip_led(void *player, void *led_stat)
{
    static const struct stems_rgb instrumental_rgb = {255u, 0u, 0u};
    static const struct stems_rgb vocal_rgb = {0u, 255u, 0u};
    original_check_slip_led(player, led_stat);

    struct stems_deck_context *context = context_for_player(player);
    if (!context || !context->reader || !context->armed)
        return;
    uint16_t count = *(const uint16_t *)((const uint8_t *)led_stat + 4u);
    uint8_t *entries = *(uint8_t **)((uint8_t *)led_stat + 8u);
    if (!entries || count > 256u)
        return;

    int loading = !context->vocal.data;
    unsigned int origin = blink_origin_ms();
    enum stem_mode selected = context->mode;
    int instrumental_on = (selected & MODE_INSTRUMENTAL) != 0;
    int vocal_on = (selected & MODE_VOCAL) != 0;
    uint32_t deck_channel = (uint32_t)(context - stems_decks) + 1u;

    for (uint16_t i = 0; i < count; i++) {
        uint8_t *led = entries + (size_t)i * 44u;
        uint32_t id = *(const uint32_t *)led;
        uint32_t channel = *(const uint32_t *)(led + 4u);
        if (channel != deck_channel)
            continue;
        const struct stems_rgb *colour;
        int lit;
        if (id == 24u) {
            colour = &instrumental_rgb;
            lit = instrumental_on;
        } else if (id == 25u) {
            colour = &vocal_rgb;
            lit = vocal_on;
        } else {
            continue;
        }
        if (loading) {
            ((set_led_state_fn)SET_LED_STATE)(led, LED_BLINK, BLINK_PERIOD_MS,
                                              origin, 0, 0);
            ((set_led_color_fn)SET_LED_COLOR)(led, LED_BLINK, 0, colour);
        } else {
            ((set_led_color_fn)SET_LED_COLOR)(led, LED_ON, lit ? 0 : 1,
                                              colour);
        }
    }
}

static void stems_feature_track_will_load(unsigned int deck, void *reader,
                                          const void *track_info)
{
    (void)reader;
    struct stems_deck_context *context = &stems_decks[deck];
    context->pending_path[0] = '\0';
    context->pending_has_sidecar =
        !sidecar_path_for_track(track_info, context->pending_path,
                                sizeof(context->pending_path)) &&
        sidecar_is_readable(context->pending_path);

    /* The old audio thread may continue until stock load stops it. Detach its
       lookup first; the payload remains allocated until track_did_load. */
    context->reader = 0;
}

static void stems_feature_track_did_load(unsigned int deck, void *reader,
                                         const void *track_info)
{
    (void)track_info;
    struct stems_deck_context *context = &stems_decks[deck];
    int has_sidecar = context->pending_has_sidecar;
    context->generation++;
    context->armed = has_sidecar;
    release_payload(&context->vocal);
    context->mode = MODE_BOTH;
    context->rendered_mode = MODE_BOTH;
    context->transition_from = MODE_BOTH;
    context->transition_to = MODE_BOTH;
    context->transition_cursor = TRANSITION_FRAMES;
    __sync_synchronize();
    context->reader = reader;

    if (!has_sidecar)
        return;
    struct stems_load_request *request = mmap(
        0, 4096u, PROT_READ | PROT_WRITE,
        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (request == MAP_FAILED) {
        log_line("sidecar disabled: request allocation failed");
        return;
    }
    request->context = context;
    request->reader = reader;
    request->generation = context->generation;
    size_t path_length = str_length(context->pending_path) + 1u;
    memcpy(request->path, context->pending_path, path_length);
    pthread_t thread;
    if (!pthread_create(&thread, 0, sidecar_loader, request)) {
        pthread_detach(thread);
        log_number("asynchronous sidecar load started, deck = ", deck + 1u);
    } else {
        munmap(request, 4096u);
        log_line("sidecar disabled: loader thread creation failed");
    }
}

static int stems_feature_configured(void)
{
    return stems_dir != 0;
}

static int stems_feature_install(void)
{
    original_get_stream = (get_stream_fn)install_hook(
        &get_stream_hook, GET_STREAM_AT, get_stream_guard,
        (void *)hooked_get_stream);
    original_on_key_pad = (on_key_pad_fn)install_hook(
        &pad_hook, ON_KEY_PAD, pad_guard, (void *)hooked_on_key_pad);
    original_check_slip_led = (check_slip_led_fn)install_pc_ldr_hook(
        &slip_led_hook, CHECK_SLIP_LED, slip_led_guard,
        (void *)hooked_check_slip_led);
    return original_get_stream && original_on_key_pad &&
           original_check_slip_led;
}

static void stems_feature_remove(void)
{
    uninstall_hook(&slip_led_hook);
    uninstall_hook(&pad_hook);
    uninstall_hook(&get_stream_hook);
    original_check_slip_led = 0;
    original_on_key_pad = 0;
    original_get_stream = 0;
}

static void stems_feature_destroy_deck(unsigned int deck)
{
    release_payload(&stems_decks[deck].vocal);
}

#endif /* RX3_STEMS_FEATURE_H */
