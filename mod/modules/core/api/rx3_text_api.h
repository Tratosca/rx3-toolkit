/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_TEXT_API_H
#define RX3_TEXT_API_H
#include "rx3_platform.h"

/* Borrowed render-thread context for one native text draw. The native colour
 * is the glyph's stored value; effective_colour is its resolved window colour.
 * A policy returns the native colour to use for this draw only. */
struct rx3_text_draw {
    unsigned int layer;
    uint16_t box[4];
    unsigned int native_colour;
    unsigned int effective_colour;
    unsigned int window_format;
    const uint32_t *palette;
    /* Native visible-list cursor (zero-based), shared by BROWSE and UTILITY. */
    unsigned int selection_index;
    /* Native list state flags, including whether the list owns focus. */
    unsigned int list_flags;
};
struct rx3_text_policy {
    unsigned int (*colour)(const struct rx3_text_draw *);
};
struct rx3_text_service {
    /* One process-lifetime owner. Claim/release during module start/stop.
       The callback runs on the render thread; no allocation, I/O or wait. */
    int (*claim)(const void *owner, const struct rx3_text_policy *);
    void (*release)(const void *owner);
    /* Render thread at the mode-switch boundary. Queues native text redraw. */
    void (*invalidate)(void);
};
extern const struct rx3_text_service rx3_text;
#endif
