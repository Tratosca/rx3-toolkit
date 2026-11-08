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
/* Where the theme turns the surface under native text light: the lists of
   BROWSE, UTILITY and SOURCE, and on HOME only each deck strip's track title
   row and the left column's track lines. HOME's own cells stay dark. */
static unsigned int theme_text_light_surface(unsigned int view, unsigned int layer,
                                             unsigned int top)
{
    if (view == 3u || view == 7u || view == 12u) return 1u;
    return view == 1u &&
        (((layer == 0x201u || layer == 0x301u) && top < 50u) || layer == 0x1101u);
}
/* Neutral ink goes dark on those light surfaces. Ink over a vivid selection
   fill, and every semantic colour, stays native. */
static unsigned int theme_text_colour(unsigned int light, unsigned int light_surface,
                                      unsigned int native_colour,
                                      unsigned int selected_background)
{
    if (light && light_surface && theme_text_neutral(native_colour) && !selected_background)
        return THEME_TEXT_DARK;
    return native_colour;
}
/* A UTILITY edit moves its blue fill from the name to the value without
   redrawing the name. Return the visible name row to queue, one-based so zero
   means no new repaint. */
static unsigned int theme_utility_name_row(unsigned int previous, unsigned int cell)
{
    unsigned int row = cell >> 2;
    return cell != previous && (cell & 3u) == 2u && row < 12u ? row + 1u : 0u;
}
#endif
