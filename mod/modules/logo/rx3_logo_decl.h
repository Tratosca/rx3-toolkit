/* SPDX-License-Identifier: MPL-2.0
 * Private logo state and the on-disk artwork format.
 */

#ifndef RX3_LOGO_DECL_H
#define RX3_LOGO_DECL_H

/* The artwork the player draws in the middle of the performance screen, and
 * the light variant it swaps to. Both are RGB565, one little-endian word per
 * pixel, row by row, behind a header that carries their size.
 */
#define LOGO_MAGIC "RX3LOGO1"

/* Artwork written before the header existed has no way to declare a size, so
 * a file that does not start with the magic is read as this and nothing else.
 */
#define LOGO_LEGACY_WIDTH 492u
#define LOGO_LEGACY_HEIGHT 70u

/* The largest pane the screen offers. Artwork beyond it is refused rather than
 * clipped: the edges would be dropped without the operator being told, and a
 * logo that silently loses its own border reads as a broken conversion.
 */
#define LOGO_MAX_WIDTH 888u
#define LOGO_MAX_HEIGHT 445u

/* One pixel, in the format the framebuffer already holds. */
#define LOGO_BYTES_PER_PIXEL 2u

struct __attribute__((packed)) logo_header {
    char magic[8];
    uint32_t width;
    uint32_t height;
};

/* The record the player already uses for the wordmark in the middle of the
 * performance screen. Replacing it rather than adding one keeps every drawing
 * decision, placement included, where the firmware already makes it.
 */
#define LOGO_IMAGE_INDEX 0x63fu

#endif /* RX3_LOGO_DECL_H */
