/* SPDX-License-Identifier: MPL-2.0
 * Logo implementation of the core runtime-feature lifecycle.
 */

#ifndef RX3_LOGO_FEATURE_H
#define RX3_LOGO_FEATURE_H
#include "rx3_logo_geometry.h"

/* Set in initialize() from RX3_LOGO, the way every other feature reads its
 * own flag; the module exports it only when the artwork reached the drive.
 */
static int logo_enabled;
static uint32_t main_logo_width;
static uint32_t main_logo_height;
static void *main_logo_pixels;
static void *main_logo_light_pixels;
static int main_logo_ready;
static int main_logo_light_ready;

/* Read one artwork file into an anonymous mapping the player can draw from.
 *
 * The mapping is anonymous rather than a mapping of the file: the artwork sits
 * on the RAM copy of /root/pdj, which the module rewrites on every insertion,
 * and a file-backed mapping would show the player half of a replacement while
 * it was still being written.
 *
 * Returns the pixels and fills the size, or null with the reason on the log.
 */
static void *load_logo(const char *path, uint32_t *width_out, uint32_t *height_out)
{
    int fd = open(path, O_RDONLY);
    if (fd < 0)
        return 0;

    /* Artwork that declares nothing is the one size that predates the header,
     * so a failed or unrecognised read falls back rather than failing.
     */
    struct logo_header header;
    uint32_t width = LOGO_LEGACY_WIDTH;
    uint32_t height = LOGO_LEGACY_HEIGHT;
    off_t offset = 0;
    if (!read_exactly(fd, &header, sizeof(header)) &&
        !memcmp(header.magic, LOGO_MAGIC, sizeof(header.magic))) {
        width = header.width;
        height = header.height;
        offset = (off_t)sizeof(header);
    }

    if (!width || width > LOGO_MAX_WIDTH || !height || height > LOGO_MAX_HEIGHT) {
        close(fd);
        log_line("logo refused: bigger than the canvas it is clipped to - its "
                 "edges would not be drawn");
        log_number("  width  =", width);
        log_number("  height =", height);
        return 0;
    }

    if (lseek(fd, offset, SEEK_SET) != offset) {
        close(fd);
        return 0;
    }

    size_t length = (size_t)width * height * LOGO_BYTES_PER_PIXEL;
    void *pixels = mmap(0, length, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (pixels == MAP_FAILED) {
        close(fd);
        log_line("logo refused: no room for its pixels");
        return 0;
    }
    if (read_exactly(fd, pixels, length)) {
        munmap(pixels, length);
        close(fd);
        log_line("logo refused: the file is shorter than it claims");
        return 0;
    }

    close(fd);
    *width_out = width;
    *height_out = height;
    return pixels;
}

static int logo_feature_install(void)
{
    if (!logo_enabled)
        return 0;

    main_logo_pixels = load_logo("/root/pdj/rx3-logo-main.rgb565",
                                 &main_logo_width, &main_logo_height);
    if (!main_logo_pixels)
        return 0;
    if (!logo_place((uint32_t *)LOGO_PLACEMENT, main_logo_width, main_logo_height)) {
        munmap(main_logo_pixels, (size_t)main_logo_width * main_logo_height * LOGO_BYTES_PER_PIXEL);
        main_logo_pixels = 0;
        log_line("logo refused: unexpected native placement record");
        return 0;
    }
    main_logo_ready = 1;

    /* The light variant is drawn into the same rectangle as the dark one, so a
     * different size is not a smaller logo: it is the wrong pixels read with
     * the wrong stride. Refusing it leaves the deck showing the dark artwork
     * in both themes, which is legible; accepting it would show neither.
     */
    uint32_t light_width = 0;
    uint32_t light_height = 0;
    void *light = load_logo("/root/pdj/rx3-logo-main-light.rgb565",
                            &light_width, &light_height);
    if (!light)
        return 1;
    if (light_width != main_logo_width || light_height != main_logo_height) {
        munmap(light, (size_t)light_width * light_height * LOGO_BYTES_PER_PIXEL);
        log_line("light logo ignored: a different size from the dark one");
        return 1;
    }
    main_logo_light_pixels = light;
    main_logo_light_ready = 1;
    return 1;
}

static void logo_feature_remove(void)
{
    logo_restore_position((uint32_t *)LOGO_PLACEMENT);
    if (main_logo_pixels)
        munmap(main_logo_pixels,
               (size_t)main_logo_width * main_logo_height * LOGO_BYTES_PER_PIXEL);
    if (main_logo_light_pixels)
        munmap(main_logo_light_pixels,
               (size_t)main_logo_width * main_logo_height * LOGO_BYTES_PER_PIXEL);
    main_logo_pixels = 0;
    main_logo_light_pixels = 0;
    main_logo_ready = 0;
    main_logo_light_ready = 0;
}

/* Point the stock wordmark record at the loaded artwork.
 *
 * The logo is not a new image: it is the record the player already draws in
 * the middle of the performance screen, so the size travels with the record
 * while logo_place updates its native position before rendering starts.
 *
 * The format byte is 2 here where the tab labels use 1. Both files are RGB565,
 * and the one thing the logo does that a tab label never does is leave parts of
 * itself unpainted, so 2 reads as the variant that honours the colour key. That
 * is a reading of one released build, not a measurement: if a logo arrives with
 * a magenta rectangle around it, this byte is the first thing to try.
 */
static void install_logo_record(uint8_t *table)
{
    if (!main_logo_ready || !main_logo_pixels)
        return;
    uint8_t *record = table + LOGO_IMAGE_INDEX * 44u;
    uint16_t width = (uint16_t)main_logo_width;
    uint16_t height = (uint16_t)main_logo_height;
    uint32_t pixels = (uint32_t)(unsigned long)main_logo_pixels -
                      (uint32_t)(unsigned long)table;
    uint32_t no_palette = 0u;
    memcpy(record + 4u, &width, sizeof(width));
    memcpy(record + 6u, &height, sizeof(height));
    record[0x18u] = 2u;
    record[0x19u] = 0u;
    memcpy(record + 0x20u, &pixels, sizeof(pixels));
    memcpy(record + 0x24u, &no_palette, sizeof(no_palette));
    log_line("main logo replaces the stock wordmark");
    log_number("  width  =", width);
    log_number("  height =", height);
}

#endif /* RX3_LOGO_FEATURE_H */
