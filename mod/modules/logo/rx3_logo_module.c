/* SPDX-License-Identifier: MPL-2.0 */
/* The main-screen wordmark. The module owns the artwork, its size and its
 * native placement; the core's image service owns the tables that point at
 * it. */
#include "../core/api/rx3_module_api.h"
static const struct rx3_services *framework;
static const unsigned char logo_owner;
#define log_line framework->log_line
#define log_number framework->log_number
#include "rx3_logo_decl.h"

static int read_exactly(int fd, void *destination, size_t length)
{
    uint8_t *cursor = destination;
    while (length) {
        ssize_t got = read(fd, cursor, length > 0x100000u ? 0x100000u : length);
        if (got <= 0)
            return -1;
        cursor += got;
        length -= (size_t)got;
    }
    return 0;
}

#include "rx3_logo_feature.h"

/* The module exports RX3_LOGO=1 only when the artwork reached the drive. */
static int logo_configured(void)
{
    const char *logo = getenv("RX3_LOGO");
    return logo && logo[0] == '1';
}

static int logo_start(const struct rx3_services *services)
{
    framework = services;
    if (!services->images || !services->images->replace_native) return 0;
    /* Read once at startup: the artwork has no controls, and the player asks
       for it while it builds the screen rather than when a deck loads. */
    if (!logo_feature_install()) {
        log_line("module failed: logo artwork or placement");
        return 0;
    }
    if (!services->images->replace_native(&logo_owner, LOGO_IMAGE_INDEX,
                                          main_logo_pixels,
                                          main_logo_light_ready ? main_logo_light_pixels : 0,
                                          main_logo_width, main_logo_height)) {
        log_line("module failed: logo image could not be registered");
        return 0;
    }
    log_line("main logo replaces the stock wordmark");
    log_number("  width  =", main_logo_width);
    log_number("  height =", main_logo_height);
    return 1;
}

static void logo_stop(void)
{
    if (!framework || !framework->images) return;
    logo_feature_remove(framework->images->release_native(&logo_owner));
}

const struct rx3_module rx3_logo_module = {
    .version = RX3_MODULE_API_VERSION, .size = sizeof(struct rx3_module),
    .name = "logo", .configured = logo_configured,
    .start = logo_start, .stop = logo_stop
};
