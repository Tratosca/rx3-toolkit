/* SPDX-License-Identifier: MPL-2.0 */
#include "rx3_text.h"

static const void *policy_owner;
static const struct rx3_text_policy *policy;

static int claim(const void *owner, const struct rx3_text_policy *wanted)
{
    if (!owner || !wanted || !wanted->colour || policy_owner) return 0;
    policy = wanted;
    __atomic_store_n(&policy_owner, owner, __ATOMIC_RELEASE);
    return 1;
}
static void release(const void *owner)
{
    if (owner != policy_owner) return;
    __atomic_store_n(&policy_owner, 0, __ATOMIC_RELEASE);
    policy = 0;
}
static void invalidate(void)
{
#if defined(__arm__)
    void *root = *(void **)0x02684700u;
    if (root) {
        void *manager = ((void *(*)(void))0x001d09b4u)();
        ((void (*)(void *, int, void *))0x001d07b0u)(manager, -1, root);
    }
#endif
}
const struct rx3_text_service rx3_text = {claim, release, invalidate};

void rx3_text_draw_native(void *render, void *glyph,
                          void (*native_draw)(void *, void *))
{
    const struct rx3_text_policy *current = policy;
    if (!__atomic_load_n(&policy_owner, __ATOMIC_ACQUIRE) || !current) {
        native_draw(render, glyph);
        return;
    }
    const uint8_t *source = glyph;
    struct rx3_text_draw draw;
    /* The glyph holds a 16-bit layer; copying it into the wider field would
       leave stack bytes in the window-table index. */
    uint16_t layer;
    memcpy(&layer, source + 0x10u, sizeof(layer));
    draw.layer = layer;
    memcpy(draw.box, source + 0x18u, sizeof(draw.box));
    memcpy(&draw.native_colour, source + 0x28u, 4u);
    draw.selection_index = 0u;
    draw.list_flags = 0u;
    draw.effective_colour = draw.native_colour;
    draw.window_format = 0u;
    draw.palette = 0;
#if defined(__arm__)
    draw.selection_index = *(const uint32_t *)0x05b528ecu;
    draw.list_flags = *(const uint8_t *)0x0551ab2bu;
    unsigned int slot = ((draw.layer & 0xffu) << 8) | (draw.layer >> 8);
    const uint32_t *const *windows = (const uint32_t *const *)0x05a15f68u;
    const uint32_t *window = windows[slot];
    if (window) {
        draw.window_format = window[2];
        if (draw.window_format == 2u && window[4]) {
            const uint32_t *palette = (const uint32_t *)(unsigned long)window[4];
            draw.palette = palette;
            draw.effective_colour = (draw.native_colour & 0xff000000u) |
                (palette[(draw.native_colour & 0xffu) + 1u] & 0x00ffffffu);
        }
    }
#endif
    unsigned int colour = current->colour(&draw);
    if (colour == draw.native_colour) {
        native_draw(render, glyph);
        return;
    }
    uint32_t copy[21];
    memcpy(copy, glyph, sizeof(copy));
    memcpy((uint8_t *)copy + 0x28u, &colour, sizeof(colour));
    native_draw(render, copy);
}
