/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_AUDIO_H
#define RX3_STEMS_AUDIO_H
#include "../core/api/rx3_dsp.h"
#include "../core/api/rx3_audio_api.h"

static unsigned int stems_available(const struct stems_deck_context *context)
{
    return (__atomic_load_n(&context->selection, __ATOMIC_SEQ_CST) >> 4u) & 7u;
}

static void stems_set_mask(struct stems_deck_context *context, unsigned int mask)
{
    uint32_t levels=0;
    for(unsigned int i=0;i<4u;i++)
        if(mask & (1u<<i)) levels |= 100u << (i*7u);
    __atomic_store_n(&context->levels, levels, __ATOMIC_SEQ_CST);
}
static unsigned int stems_selected(const struct stems_deck_context *context)
{
    uint32_t levels=__atomic_load_n(&context->levels, __ATOMIC_SEQ_CST);
    unsigned int selected=0;
    for(unsigned int i=0;i<4u;i++) if((levels>>(i*7u))&127u) selected |= 1u<<i;
    return selected & stems_available(context);
}
static unsigned int stems_level(const struct stems_deck_context *context, unsigned int bit)
{
    uint32_t levels=__atomic_load_n(&context->levels, __ATOMIC_SEQ_CST);
    for(unsigned int i=0;i<4u;i++) if(bit==(1u<<i)) return (levels>>(i*7u))&127u;
    return 0;
}
/* Both physical pads and touch clients edit this same atomic word. */
static void stems_change_levels(struct stems_deck_context *context, unsigned int bits,
                               unsigned int value, int toggle)
{
    bits &= stems_available(context);
    if(!bits) return;
    if(value>100u) value=100u;
    uint32_t old=__atomic_load_n(&context->levels, __ATOMIC_SEQ_CST);
    for(;;) {
        uint32_t next=old;
        for(unsigned int i=0;i<4u;i++) if(bits & (1u<<i)) {
            unsigned int shift=i*7u;
            unsigned int level=toggle ? (((old>>shift)&127u) ? 0u : 100u) : value;
            next=(next & ~(127u<<shift)) | (level<<shift);
        }
        if(__atomic_compare_exchange_n(&context->levels,&old,next,0,
                                      __ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST)) return;
    }
}
static void stems_toggle(struct stems_deck_context *context, unsigned int bits)
{
    stems_change_levels(context,bits,0,1);
}
static void stems_set_level(struct stems_deck_context *context, unsigned int bit,
                           unsigned int value)
{
    stems_change_levels(context,bit,value,0);
}

static void stems_reset_mix(struct stems_deck_context *context)
{
    for (unsigned int i = 0; i < 4u; i++)
        context->gain[i] = context->from[i] = context->target[i] = 1.0f;
    context->transition_cursor = 256u;
    stems_set_mask(context, context->selection & 15u);
}

static void stems_mix(struct stems_deck_context *context, int position,
                        struct rx3_stereo *output, unsigned int frames)
{
#ifdef RX3_OVERCUE_PROTOTYPE
    if(context->overcue) {
        if(position>=0)rx3_overcue_render((unsigned int)(context-stems_decks),
            (unsigned int)position,output,frames,stems_selected(context));
        return;
    }
#endif
    unsigned int count = context->payload_count;
    if (!output || !frames || !count || count > 3u || !context->payloads[0].data) return;
    uint32_t levels = __atomic_load_n(&context->levels, __ATOMIC_SEQ_CST);
    float target[4];
    int changed = 0, all = 1;
    for (unsigned int i = 0; i <= count; i++) {
        /* Legacy bass payloads remain part of INST. */
        target[i] = (float)((levels >> ((i == 3u ? 0u : i) * 7u)) & 127u) * 0.01f;
        if (target[i] != context->target[i]) changed = 1;
        if (target[i] != 1.0f) all = 0;
    }
    if (changed) {
        for (unsigned int i = 0; i <= count; i++) {
            context->from[i] = context->gain[i];
            context->target[i] = target[i];
        }
        context->transition_cursor = 0u;
    } else if (context->transition_cursor >= 256u) {
        for (unsigned int i = 0; i <= count; i++) context->gain[i] = target[i];
        if (all) return;
    }
    uint64_t limit = context->payloads[0].frames;
    for (unsigned int i = 1; i < count; i++)
        if (context->payloads[i].frames < limit) limit = context->payloads[i].frames;
    for (unsigned int i = 0; i < frames; i++) {
        int index = (int)((uint32_t)position + i);
        if (index < 0 || (uint64_t)(unsigned int)index >= limit) continue;
        if (output[i].left == 0.0f && output[i].right == 0.0f) continue;
        if (context->transition_cursor < 256u) {
            float alpha = (float)++context->transition_cursor * (1.0f / 256.0f);
            for (unsigned int j = 0; j <= count; j++)
                context->gain[j] = rx3_dsp_lerp(context->from[j], context->target[j], alpha);
        }
        float residual = context->gain[0];
        struct rx3_stereo mixed = {output[i].left * residual, output[i].right * residual};
        for (unsigned int j = 0; j < count; j++) {
            const Short2 *pcm = (const Short2 *)context->payloads[j].data + (unsigned int)index;
            float gain = (context->gain[j + 1u] - residual) * (1.0f / 32768.0f);
            float scale = context->payloads[j].format == FORMAT_S16_GAIN ? context->payloads[j].pcm_gain : 1.0f;
            float left = (float)pcm->left * scale, right = (float)pcm->right * scale;
            mixed.left += left * gain;
            mixed.right += right * gain;
        }
        output[i] = mixed;
        if (context->transition_cursor >= 256u)
            for (unsigned int j = 0; j <= count; j++) context->gain[j] = context->target[j];
    }
}

#endif /* RX3_STEMS_AUDIO_H */
