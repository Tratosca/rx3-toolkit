/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_FEATURE_H
#define RX3_STEMS_FEATURE_H

#include "rx3_stems_loader.h"

static int block_is_silent(const struct rx3_stereo *output, unsigned int frames)
{
    for (unsigned int i = 0; i < frames; i++)
        if (output[i].left != 0.0f || output[i].right != 0.0f)
            return 0;
    return 1;
}

/* Audio thread, after the deck's TimeStretch stage. The reader check keeps a
   stale request from mixing into the next track. */
static void stems_stream(unsigned int deck, const void *reader, int position,
                         struct rx3_stereo *output, unsigned int frames)
{
    if (deck >= 2u || !__atomic_load_n(&stems_callbacks_enabled, __ATOMIC_SEQ_CST)) return;
    struct stems_deck_context *context = &stems_decks[deck];
    __sync_add_and_fetch(&context->readers_active, 1u);
    if (__atomic_load_n(&context->reader, __ATOMIC_SEQ_CST) == reader &&
        !block_is_silent(output, frames))
        stems_mix(context, position, output, frames);
    __sync_sub_and_fetch(&context->readers_active, 1u);
}

/* SLIP LOOP pads 5 to 8 toggle the prepared roles once the set is resident.
   A captured press also takes its release, so the native loop never sees half
   of a gesture. */
static int stems_pad(const struct rx3_pad_event *event)
{
    unsigned int code = event->code;
    if (!__atomic_load_n(&stems_callbacks_enabled, __ATOMIC_SEQ_CST) ||
        code < 0x411bu || code > 0x411eu || event->deck >= 2u) return 0;
    unsigned int operation = event->operation;
    unsigned int deck = event->deck, pad = code - 0x411bu, captured = 1u << pad;
    struct stems_deck_context *context = &stems_decks[deck];
    unsigned int bit = stems_display_order[pad];
    if (!operation && event->pad_mode == 2u &&
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
    return 0;
}

/* SLIP LOOP pads 5 to 8 blink while the set loads, then hold their role
   colour, dimmed when the role is off. Pads without a role stay native. */
static void stems_light(unsigned int deck, unsigned int control, struct rx3_light *light)
{
    if (deck >= 2u || control < 4u || control > 7u) return;
    struct stems_deck_context *context = &stems_decks[deck];
    if (!__atomic_load_n(&stems_callbacks_enabled, __ATOMIC_SEQ_CST) ||
        !context->reader || !context->armed) return;
    unsigned int pad = control - 4u, bit = stems_display_order[pad];
    if (!(stems_available(context) & bit)) return;
    const struct stems_rgb *c = &stems_pad_colour[pad];
    light->rgb = ((uint32_t)c->red << 16u) | ((uint32_t)c->green << 8u) | c->blue;
    if (!context->payloads[0].data)
        light->state = RX3_LIGHT_BLINK;
    else
        light->state = stems_selected(context) & bit ? RX3_LIGHT_ON : RX3_LIGHT_DIM;
    if (!stems_any_deck_loading()) stems_blink_idle();
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
    for (unsigned int i = 0; i < 2u; i++) {
        stems_decks[i].selection = 0u;
        stems_decks[i].transition_cursor = TRANSITION_FRAMES;
    }
    if (!framework->audio->claim_deck_stream(&stems_decks, stems_stream) ||
        !framework->input->register_pad(&stems_decks, 20u, stems_pad) ||
        !framework->input->register_lights(&stems_decks, RX3_LIGHTS_SLIP_LOOP, stems_light) ||
        !framework->loader->claim(&stems_decks)) return 0;
    if (!framework->provide_mix(stems_mix_state) ||
        !framework->provide_waveform(stems_waveform)) return 0;
    __atomic_store_n(&stems_callbacks_enabled, 1u, __ATOMIC_SEQ_CST);
    return framework->panels->register_row(&stems_row);
}

/* The core detaches and drains the shared stream, pad and LED hooks before
   these calls return; the deck drains below cover the waveform readers. */
static void stems_feature_remove(void)
{
    framework->withdraw_waveform(stems_waveform);
    framework->withdraw_mix(stems_mix_state);
    __atomic_store_n(&stems_callbacks_enabled, 0u, __ATOMIC_SEQ_CST);
    framework->panels->unregister_row(&stems_row);
    framework->audio->release_deck_stream(&stems_decks);
    framework->input->unregister_owner(&stems_decks);
    /* Queued loads are dropped and a running one finishes before this
       returns; pending requests are released below. */
    framework->loader->release(&stems_decks);
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
}

#endif /* RX3_STEMS_FEATURE_H */
