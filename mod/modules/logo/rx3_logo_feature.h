/* SPDX-License-Identifier: MPL-2.0
 * Logo artwork loading and placement, private to rx3_logo_module.c.
 */

#ifndef RX3_LOGO_FEATURE_H
#define RX3_LOGO_FEATURE_H
#include "rx3_logo_geometry.h"

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

/* Once a published image table references the artwork, it and its placement
   stay for the life of the process. */
static void logo_feature_remove(int release_pixels)
{
    if (!release_pixels) {
        log_line("logo retained: the published image table references it");
        return;
    }
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

#endif /* RX3_LOGO_FEATURE_H */
