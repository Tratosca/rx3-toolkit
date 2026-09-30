/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_THEME_PIXELS_H
#define RX3_THEME_PIXELS_H

/* The two per-pixel conversions and what they are decided from.
 *
 * Nothing here reads a player address or writes a log, so a host compiles
 * and runs it. tests/test_theme_pixels.py does exactly that, which is the
 * only way either conversion gets checked without a deck in front of you.
 */

/* Split one RGB565 word into eight-bit channels, as the panel expands it. */
static void theme_unpack(uint16_t pixel, unsigned int *red, unsigned int *green,
                         unsigned int *blue)
{
    *red = (unsigned int)(pixel >> 8) & 0xf8u;
    *green = (unsigned int)(pixel >> 3) & 0xfcu;
    *blue = ((unsigned int)pixel & 0x1fu) * 8u;
}

static uint16_t theme_pack(unsigned int red, unsigned int green, unsigned int blue)
{
    uint16_t packed = (uint16_t)(((red & 0xf8u) << 8) | ((green & 0xfcu) << 3) |
                                 (blue >> 3));
    /* One step of green off the colour key, the same nudge the logo container
       makes. A pixel that lands on the key would be punched out of the image
       it belongs to. */
    return packed == COLOUR_KEY ? (uint16_t)(packed | 1u << 5) : packed;
}

static unsigned int theme_spread(unsigned int red, unsigned int green,
                                 unsigned int blue)
{
    unsigned int high = red > green ? red : green;
    unsigned int low = red < green ? red : green;
    if (blue > high)
        high = blue;
    if (blue < low)
        low = blue;
    return high - low;
}

static unsigned int theme_luma(unsigned int red, unsigned int green,
                               unsigned int blue)
{
    return (red * THEME_LUMA_RED + green * THEME_LUMA_GREEN +
            blue * THEME_LUMA_BLUE) >> 8;
}

/* Whether this bitmap carries a picture rather than interface furniture.
 *
 * Counted rather than declared: a quarter of the opaque pixels being vivid is
 * what separates a sleeve or a waveform from a button. Chrome is what the
 * theme exists to repaint, and repainting a picture would be vandalism.
 */
static inline int theme_is_artwork(const uint16_t *pixels, unsigned int count)
{
    unsigned int opaque = 0;
    unsigned int vivid = 0;
    for (unsigned int index = 0; index < count; index++) {
        uint16_t pixel = pixels[index];
        if (pixel == COLOUR_KEY)
            continue;
        unsigned int red;
        unsigned int green;
        unsigned int blue;
        theme_unpack(pixel, &red, &green, &blue);
        opaque++;
        if (theme_spread(red, green, blue) > THEME_VIVID_SPREAD)
            vivid++;
    }
    return opaque != 0 && opaque * THEME_ARTWORK_PERCENT <= vivid * 100u;
}

/* One pixel, for a lit room.
 *
 * Artwork keeps its hue and only loses the glare. Chrome is inverted into a
 * bounded grey, so what was near black becomes near white without either end
 * reaching the extremes: a pane needs its edges to stay visible.
 *
 * Between the two there is a band where a pixel is neither clearly neutral nor
 * clearly a colour, and it is blended rather than forced. That is what stops a
 * pale tint turning green while a status colour keeps its meaning.
 */
static uint16_t theme_pixel_light_for_image(unsigned int image, uint16_t pixel, int artwork)
{
    if ((image == 0xa3fu || image == 0xa60u || image == 0xa81u || image == 0xaa1u) &&
        pixel == 0x3907u) return 0xce59u;
    if ((image == 0xa40u || image == 0xa61u || image == 0xa82u || image == 0xaa2u) &&
        pixel == 0x28e6u) return 0xdedbu;
    if (pixel == COLOUR_KEY)
        return pixel;
    unsigned int red;
    unsigned int green;
    unsigned int blue;
    theme_unpack(pixel, &red, &green, &blue);
    unsigned int spread = theme_spread(red, green, blue);
    unsigned int luma = theme_luma(red, green, blue);

    unsigned int toned_red = red;
    unsigned int toned_green = green;
    unsigned int toned_blue = blue;
    if (luma > THEME_LUMA_CEILING) {
        toned_red = red * THEME_LUMA_CEILING / luma;
        toned_green = green * THEME_LUMA_CEILING / luma;
        toned_blue = blue * THEME_LUMA_CEILING / luma;
    }
    if (artwork || spread > THEME_LIGHT_SPREAD)
        return theme_pack(toned_red, toned_green, toned_blue);

    unsigned int low = red < green ? red : green;
    if (blue < low)
        low = blue;
    if (low > 0x7fu && spread < THEME_LIGHT_SPREAD) {
        /* A light neutral already: it only has to change ends, not hue. */
        unsigned int value = THEME_GREY_FLOOR +
                             (0xffu - luma) * THEME_GREY_SPAN / 0xffu;
        return theme_pack(value, value, value);
    }

    unsigned int grey_red = THEME_GREY_FLOOR +
                            (red ^ 0xffu) * THEME_GREY_SPAN / 0xffu;
    unsigned int grey_green = THEME_GREY_FLOOR +
                              (green ^ 0xffu) * THEME_GREY_SPAN / 0xffu;
    unsigned int grey_blue = THEME_GREY_FLOOR +
                             (blue ^ 0xffu) * THEME_GREY_SPAN / 0xffu;
    if (spread < THEME_NEUTRAL_SPREAD)
        return theme_pack(grey_red, grey_green, grey_blue);

    /* The band between: how far into it the pixel sits decides how much of its
       own colour survives the inversion. */
    unsigned int weight = (spread - THEME_BLEND_BASE) * THEME_BLEND_STEP;
    unsigned int rest = THEME_BLEND_TOTAL - weight;
    return theme_pack((toned_red * weight + grey_red * rest) >> 8,
                      (toned_green * weight + grey_green * rest) >> 8,
                      (toned_blue * weight + grey_blue * rest) >> 8);
}

/* One pixel, for a dark room.
 *
 * The mirror of the light conversion, and a narrower one. A pixel with any
 * real colour in it is left alone: only what is already grey is taken down to
 * roughly a third of its brightness, which is what turns the stock chrome
 * black without touching a status colour or a sleeve.
 *
 * The three channels share one multiplier. Read from the disassembly at
 * 0003164c, where the shifts differ per channel but the constant does not.
 */
static uint16_t theme_pixel_dark(uint16_t pixel)
{
    unsigned int green = (unsigned int)(pixel >> 3) & 0xfcu;
    unsigned int red = (unsigned int)(pixel >> 8) & 0xf8u;
    unsigned int blue = ((unsigned int)pixel << 3) & 0xffu;
    unsigned int high = red > green ? red : green;
    unsigned int low = red > green ? green : red;
    if (low > blue)
        low = blue;
    if (high < blue)
        high = blue;
    if (pixel == COLOUR_KEY)
        return pixel;
    if (high - low > THEME_DARK_SPREAD)
        return pixel;
    return (uint16_t)((((red * THEME_DARK_SCALE) >> 11) & 0x7800u) |
                      ((blue * THEME_DARK_SCALE) >> 22) |
                      (((green * THEME_DARK_SCALE) >> 16) & ~0x1fu));
}

#endif
