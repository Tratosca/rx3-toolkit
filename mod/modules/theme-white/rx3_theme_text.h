/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_THEME_TEXT_H
#define RX3_THEME_TEXT_H

/* Native style zero and near-white ARGB are neutral ink. Selected rows keep
 * their native contrast; semantic colours stay native. */
#define THEME_TEXT_DARK 0xff252525u
static unsigned int theme_text_neutral(unsigned int colour)
{
    if (colour == 0u) return 1u;
    if ((colour & 0xff000000u) != 0xff000000u) return 0u;
    unsigned int r = (colour >> 16) & 0xffu;
    unsigned int g = (colour >> 8) & 0xffu;
    unsigned int b = colour & 0xffu;
    unsigned int high = r > g ? r : g;
    unsigned int low = r < g ? r : g;
    if (b > high) high = b;
    if (b < low) low = b;
    return low >= 0xc0u && high - low <= 0x18u;
}
/* Neutral ink goes dark on the light surfaces of BROWSE, UTILITY and SOURCE.
   Ink over a vivid selection fill, and every semantic colour, stays native. */
static unsigned int theme_text_colour(unsigned int light, unsigned int view,
                                      unsigned int native_colour,
                                      unsigned int selected_background)
{
    if (light && (view == 3u || view == 7u || view == 12u) &&
        theme_text_neutral(native_colour) && !selected_background)
        return THEME_TEXT_DARK;
    return native_colour;
}
#endif
