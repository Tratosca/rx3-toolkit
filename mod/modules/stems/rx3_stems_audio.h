/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_STEMS_AUDIO_H
#define RX3_STEMS_AUDIO_H

static unsigned int stems_available(const struct stems_deck_context *context)
{
    return (__atomic_load_n(&context->selection, __ATOMIC_SEQ_CST) >> 4u) & 15u;
}

static void stems_toggle(struct stems_deck_context *context, unsigned int bit)
{
    unsigned int packed = __atomic_load_n(&context->selection, __ATOMIC_SEQ_CST);
    for (;;) {
        unsigned int change = bit & (packed >> 4u) & 15u;
        if (!change) return;
        unsigned int next = (packed & ~15u) + ((packed & 15u) ^ change) + 0x100u;
        if (__atomic_compare_exchange_n(&context->selection, &packed, next, 0,
                                         __ATOMIC_SEQ_CST, __ATOMIC_SEQ_CST)) return;
    }
}

static void stems_reset_mix(struct stems_deck_context *context)
{
    for (unsigned int i = 0; i < 4u; i++)
        context->gain[i] = context->from[i] = context->target[i] = 1.0f;
    context->transition_cursor = 256u;
}

static void stems_mix(struct stems_deck_context *context, int position,
                        Float2 *output, unsigned int frames)
{
    unsigned int count = context->payload_count;
    if (!output || !frames || !count || count > 3u || !context->payloads[0].data) return;
    unsigned int selected = __atomic_load_n(&context->selection, __ATOMIC_SEQ_CST) & 15u;
    float target[4];
    int changed = 0, all = 1;
    for (unsigned int i = 0; i <= count; i++) {
        target[i] = (selected & (1u << i)) ? 1.0f : 0.0f;
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
                context->gain[j] = context->from[j] + (context->target[j] - context->from[j]) * alpha;
        }
        float residual = context->gain[0];
        Float2 mixed = {output[i].left * residual, output[i].right * residual};
        for (unsigned int j = 0; j < count; j++) {
            const Short2 *pcm = (const Short2 *)context->payloads[j].data + (unsigned int)index;
            float gain = (context->gain[j + 1u] - residual) * (1.0f / 32768.0f);
            mixed.left += (float)pcm->left * gain;
            mixed.right += (float)pcm->right * gain;
        }
        output[i] = mixed;
        if (context->transition_cursor >= 256u)
            for (unsigned int j = 0; j <= count; j++) context->gain[j] = context->target[j];
    }
}

#endif /* RX3_STEMS_AUDIO_H */
