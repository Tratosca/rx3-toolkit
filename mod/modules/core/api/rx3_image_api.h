/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_IMAGE_API_H
#define RX3_IMAGE_API_H
#include "rx3_platform.h"
/* The core owns the native image tables: it builds the private extended
 * table, publishes it, keeps an optional light variant and selects between
 * them. Modules contribute pixels and policy; they never write a table.
 *
 * Immutable small RGB565 variants; owner and registration have process lifetime.
 * Zero is failure. Unregister only after the module's callers have drained. */

/* Stock records the player ships: native_image() and publish_variant()
   accept IDs below this. */
#define RX3_NATIVE_IMAGE_COUNT 0x15cdu

/* A stock record as the dark table holds it. `pixels` is absolute. */
struct rx3_native_image {
    unsigned int width, height, format, paletted;
    const uint16_t *pixels;
};

/* Display-mode policy, supplied by one owner. Both callbacks run on the
 * render thread and must not allocate, perform I/O or wait. */
struct rx3_image_policy {
    /* A stock image is about to be drawn. */
    void (*drawn)(unsigned int image);
    /* A solid fill while the light variant is shown, outside the core's own
       panel painting. Colour: blue bits 0-4, green 8-13, red 16-20. Return
       the colour to fill with. */
    unsigned int (*fill)(unsigned int colour, unsigned int width, unsigned int height);
};

struct rx3_image_service {
    unsigned int (*register_recolour)(const void *owner, unsigned int source,
                                      uint16_t from, uint16_t to);
    void (*unregister_owner)(const void *owner);
    /* Copies raw RGB565 pixels; native colour-key format follows source. */
    unsigned int (*register_bitmap)(const void *owner,unsigned int source,
        const uint16_t *pixels,unsigned int width,unsigned int height);
    /* Replace one stock record with colour-keyed RGB565 pixels (format 2).
       `light` may be null. Register before the performance tables are built.
       The pixels stay referenced by the published table: release_native
       returns nonzero only while nothing has published them, and only then
       may the caller free them. */
    int (*replace_native)(const void *owner, unsigned int image,
                          const uint16_t *dark, const uint16_t *light,
                          unsigned int width, unsigned int height);
    int (*release_native)(const void *owner);
    /* One policy owner. Claiming requests a light table and installs the
       shared fill adapter; release selects the dark table again. */
    int (*claim_variants)(const void *owner, const struct rx3_image_policy *);
    void (*release_variants)(const void *owner);
    /* Nonzero once both tables exist. */
    int (*variants_ready)(void);
    /* Render thread. Private, replaced and table-resident records return 0. */
    int (*native_image)(unsigned int image, struct rx3_native_image *);
    /* Render thread. Point the light record at resident converted pixels. */
    int (*publish_variant)(unsigned int image, const uint16_t *pixels);
    /* Render thread, at a render-pass boundary. */
    void (*select_variant)(int light);
    int (*light_active)(void);
};
extern const struct rx3_image_service rx3_images;
#endif
