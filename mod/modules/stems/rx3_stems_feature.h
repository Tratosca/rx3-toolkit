/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_FEATURE_H
#define RX3_STEMS_FEATURE_H

#include "rx3_stems_loader.h"

static unsigned long hooked_get_stream(void *stretch, unsigned long position,
                                       Float2 *output, unsigned long frames)
{
    __sync_add_and_fetch(&stems_callbacks_active, 1u);
    unsigned long result = original_get_stream(stretch, position, output, frames);
    void *reader = *(void **)((uint8_t *)stretch + 4u);
    int deck = deck_index_for_reader(reader);
    if (deck >= 0 && __atomic_load_n(&stems_callbacks_enabled, __ATOMIC_SEQ_CST)) {
        struct stems_deck_context *context = &stems_decks[deck];
        __sync_add_and_fetch(&context->readers_active, 1u);
        if (__atomic_load_n(&context->reader, __ATOMIC_SEQ_CST) == reader &&
            output && !block_is_silent(output, frames))
            stems_mix(context, (int)position, output, frames);
        __sync_sub_and_fetch(&context->readers_active, 1u);
    }
    __sync_sub_and_fetch(&stems_callbacks_active, 1u);
    return result;
}

static int stems_on_key_pad(void *player_innards, const void *key_input)
{
    const uint8_t *event = key_input;
    unsigned int code = event[8] | ((unsigned int)event[9] << 8u);
    if (!__atomic_load_n(&stems_callbacks_enabled, __ATOMIC_SEQ_CST) ||
        code < 0x411bu || code > 0x411eu) return original_on_key_pad(player_innards, key_input);
    unsigned int operation = event[11] & 15u;
    unsigned int channel = event[10];
    if (channel < 1u || channel > 2u) channel = *((const uint8_t *)player_innards + 0x26u);
    if (channel < 1u || channel > 2u) return original_on_key_pad(player_innards, key_input);
    unsigned int deck = channel - 1u, pad = code - 0x411bu, captured = 1u << pad;
    struct stems_deck_context *context = &stems_decks[deck];
    unsigned int bit = stems_display_order[pad];
    if (!operation && *(const uint32_t *)((const uint8_t *)player_innards + 0x74u) == 2u &&
        context->status == 2u && context->reader && context->armed && (stems_available(context) & bit)) {
        __atomic_fetch_or(&captured_pad_mask[deck], captured, __ATOMIC_SEQ_CST);
        stems_toggle(context, bit);
        return 1;
    }
    if (__atomic_load_n(&captured_pad_mask[deck], __ATOMIC_SEQ_CST) & captured) {
        if (operation == 2u || operation == 3u)
            __atomic_fetch_and(&captured_pad_mask[deck], ~captured, __ATOMIC_SEQ_CST);
        return 1;
    }
    return original_on_key_pad(player_innards, key_input);
}

static void hooked_check_slip_led(void *player, void *led_stat)
{
    const struct stems_rgb *colour = stems_pad_colour;
    __sync_add_and_fetch(&pad_callbacks_active, 1u);
    original_check_slip_led(player, led_stat);
    struct stems_deck_context *context = context_for_player(player);
    if (!__atomic_load_n(&stems_callbacks_enabled, __ATOMIC_SEQ_CST) || !context ||
        !context->reader || !context->armed || !led_stat) goto done;
    unsigned int count = *(const uint16_t *)((const uint8_t *)led_stat + 4u);
    uint8_t *entries = *(uint8_t **)((uint8_t *)led_stat + 8u);
    if (!entries || count > 256u) goto done;
    unsigned int available = stems_available(context);
    unsigned int selected = stems_selected(context);
    unsigned int deck_channel = (unsigned int)(context - stems_decks) + 1u;
    int loading = !context->payloads[0].data;
    unsigned int origin = blink_origin_ms();
    for (unsigned int i = 0; i < count; i++) {
        uint8_t *led = entries + i * 44u;
        uint32_t channel = *(const uint32_t *)(led + 4u);
        if (channel != deck_channel) continue;
        unsigned int id = *(const uint32_t *)led;
        if (id < 22u || id > 25u) continue;
        unsigned int pad = id - 22u, bit = stems_display_order[pad];
        if (!(available & bit)) continue;
        if (loading) {
            ((set_led_state_fn)SET_LED_STATE)(led, LED_BLINK, BLINK_PERIOD_MS, origin, 0, 0);
            ((set_led_color_fn)SET_LED_COLOR)(led, LED_BLINK, 0, &colour[pad]);
        } else {
            ((set_led_color_fn)SET_LED_COLOR)(led, LED_ON, !(selected & bit), &colour[pad]);
        }
    }
done:
    __sync_sub_and_fetch(&pad_callbacks_active, 1u);
}

static int stems_feature_configured(void)
{
    return stems_dir != 0;
}

/* Publish values through the sharing framework, never the PCM context. */
static struct rx3_mix_state stems_mix_state(unsigned int deck)
{
    const struct stems_deck_context *context = &stems_decks[deck];
    struct rx3_mix_state state = {
        stems_selected(context), stems_available(context),
        __atomic_load_n(&context->reader, __ATOMIC_SEQ_CST) &&
        __atomic_load_n(&context->armed, __ATOMIC_SEQ_CST) &&
        __atomic_load_n(&context->payloads[0].data, __ATOMIC_SEQ_CST)
    };
    return state;
}

/* Copy under the same reader barrier as PCM. Loading/unloading never exposes
   stale package pointers to the separate Stemwave module. */
static unsigned int stems_waveform(unsigned int deck, unsigned int mask,
                                    unsigned int format, uint8_t *out, unsigned int count)
{
    if(deck>=2u || format>3u || !out) return 0;
    struct stems_deck_context *context=&stems_decks[deck];
    unsigned int copied=0, stride=format>=2u?3u:format+1u;
    __sync_add_and_fetch(&context->readers_active,1u);
    if (!__atomic_load_n(&context->reader,__ATOMIC_SEQ_CST) ||
        !context->armed) goto done;
    /* Audio without prepared waveforms must retain the native display. */
    if(context->payloads[0].data && !context->payloads[0].wave) {
        copied=0xfffffffeu; goto done;
    }
    if(!context->payloads[0].wave) goto done;
    const uint8_t *wave=context->payloads[0].wave;
    const struct rx3_wave_header *header=(const void *)wave;
    if(header->version==4u && (stride!=header->stride || format==2u)) {
        copied=0xfffffffeu; goto done;
    }
    if(count!=header->count) { copied=0xffffffffu; goto done; }
    if(mask & ~stems_available(context)) goto done;
    if(!mask) { memset(out,0,count*stride); copied=count; goto done; }
    const struct rx3_wave_entry *entries=(const void *)(wave+128u);
    if(header->version==4u) {
        if(mask>header->roles) goto done;
        memcpy(out,wave+(unsigned int)entries[mask-1u].offset,count*stride);
        copied=count;
    } else if(header->version>=2u) {
        if((format==3u && header->version!=3u) || (format==2u && header->version!=2u)) goto done;
        if(mask>header->roles) goto done;
        const uint8_t *data=wave+(unsigned int)entries[mask-1u].offset;
        unsigned int offset=format==0u?0u:format==1u?1u:3u;
        for(unsigned int i=0;i<count;i++)
            memcpy(out+i*stride,data+i*6u+offset,stride);
        copied=count;
    } else {
        /* Old files only contain single-role curves in one display format.
           Never pass an envelope sum off as the waveform of a mixed signal. */
        if(stride!=header->stride || format>=2u || (mask & (mask-1u))) goto done;
        unsigned int role=mask==2u?0u:mask==1u?1u:2u;
        if(role>=header->roles || (mask==1u && header->roles==4u)) goto done;
        memcpy(out,wave+(unsigned int)entries[role].offset,count*stride);
        copied=count;
    }
done:
    __sync_sub_and_fetch(&context->readers_active,1u);
    return copied;
}

static int stems_feature_install(void)
{
#ifdef RX3_OVERCUE_PROTOTYPE
    if(getenv("RX3_OVERCUE_ROOT")&&!rx3_overcue_start())return 0;
#endif
    original_get_stream = (get_stream_fn)install_hook(&get_stream_hook,
        TIMESTRETCH_STREAM, timestretch_stream_guard, (void *)hooked_get_stream);
    original_on_key_pad = (on_key_pad_fn)install_hook(&pad_hook, ON_KEY_PAD,
        pad_guard, (void *)hooked_on_key_pad);
    original_check_slip_led = (check_slip_led_fn)install_pc_ldr_hook(&slip_led_hook,
        CHECK_SLIP_LED, slip_led_guard, (void *)hooked_check_slip_led);
    if (!original_get_stream || !original_on_key_pad || !original_check_slip_led) return 0;
    stems_loader_running = 1u;
    if (pthread_create(&stems_loader_thread, 0, stems_loader_loop, 0)) {
        stems_loader_running = 0u;
        return 0;
    }
    stems_loader_started = 1;
    if (!rx3_mix_claim(stems_mix_state) || !rx3_wave_claim(stems_waveform)) return 0;
    __atomic_store_n(&stems_callbacks_enabled, 1u, __ATOMIC_SEQ_CST);
    return 1;
}

static void stems_feature_remove(void)
{
    rx3_wave_release(stems_waveform);
    rx3_mix_release(stems_mix_state);
    __atomic_store_n(&stems_callbacks_enabled, 0u, __ATOMIC_SEQ_CST);
    struct installed_hook *hooks[3] = {&slip_led_hook, &pad_hook, &get_stream_hook};
    int detached[3];
    for (unsigned int i = 0; i < 3u; i++)
        detached[i] = detach_hook(hooks[i]);
    for (;;) {
        while (__atomic_load_n(&stems_callbacks_active, __ATOMIC_SEQ_CST) ||
               __atomic_load_n(&pad_callbacks_active, __ATOMIC_SEQ_CST)) usleep(10000u);
        usleep(10000u);
        if (!__atomic_load_n(&stems_callbacks_active, __ATOMIC_SEQ_CST) &&
            !__atomic_load_n(&pad_callbacks_active, __ATOMIC_SEQ_CST)) break;
    }
    __atomic_store_n(&stems_loader_running, 0u, __ATOMIC_SEQ_CST);
    if (stems_loader_started) {
        pthread_join(stems_loader_thread, 0);
        stems_loader_started = 0;
    }
    for (unsigned int deck = 0; deck < 2u; deck++) {
        stems_release_request(stems_pending_loads[deck]);
        stems_pending_loads[deck] = 0;
        __atomic_store_n(&stems_decks[deck].reader, 0, __ATOMIC_SEQ_CST);
        stems_drain(&stems_decks[deck]);
        for (unsigned int i = 0; i < 3u; i++) {
            if (stems_decks[deck].pending_fds[i] >= 0) close(stems_decks[deck].pending_fds[i]);
            stems_decks[deck].pending_fds[i] = -1;
            release_payload(&stems_decks[deck].payloads[i]);
        }
        stems_decks[deck].payload_count = 0u;
    }
#ifdef RX3_OVERCUE_PROTOTYPE
    rx3_overcue_stop();
#endif
    for (unsigned int i = 0; i < 3u; i++) if (detached[i]) {
        (void)release_hook(hooks[i]);
    }
    if (detached[0]) original_check_slip_led = 0;
    if (detached[1]) original_on_key_pad = 0;
    if (detached[2]) original_get_stream = 0;
}

static void stems_feature_destroy_deck(unsigned int deck)
{
    for (unsigned int i = 0; i < 3u; i++) release_payload(&stems_decks[deck].payloads[i]);
}

#endif /* RX3_STEMS_FEATURE_H */
