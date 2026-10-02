/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_THEME_TEXT_H
#define RX3_THEME_TEXT_H

/* Native list style zero is the neutral white ink. Other values include
 * semantic colours and stay native. Selection also needs the visible cursor. */
#define THEME_TEXT_DARK 0xff252525u
static unsigned int theme_text_selected(unsigned int view, unsigned int x,
                                        unsigned int y, unsigned int index,
                                        unsigned int list_flags)
{
    unsigned int first = view == 3u ? 60u : 11u;
    unsigned int step = view == 3u ? 50u : 52u;
    return (view == 3u || view == 7u) && index < 12u && y >= first &&
        y < first + 12u * step && (y - first) / step == index &&
        (view != 3u || (list_flags & 0x10u)) &&
        (view != 7u || x < 734u);
}
static unsigned int theme_text_colour(unsigned int light, unsigned int view,
                                      unsigned int native_colour, unsigned int x,
                                      unsigned int y, unsigned int selection_index,
                                      unsigned int list_flags)
{
    if (light && (view == 3u || view == 7u) &&
        native_colour == 0u &&
        !theme_text_selected(view, x, y, selection_index, list_flags))
        return THEME_TEXT_DARK;
    return native_colour;
}
#endif
