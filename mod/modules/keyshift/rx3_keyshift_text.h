/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_KEYSHIFT_TEXT_H
#define RX3_KEYSHIFT_TEXT_H

static const char *const rx3_camelot_classic[24] = {
    "Abm", "B", "Ebm", "F#", "Bbm", "Db", "Fm", "Ab",
    "Cm", "Eb", "Gm", "Bb", "Dm", "F", "Am", "C",
    "Em", "G", "Bm", "D", "F#m", "A", "Dbm", "E"
};

/* Colours sampled from Mixed In Key's published Camelot wheel, A then B.
   https://mixedinkey.com/camelot-wheel/ — quantized to the panel's RGB565. */
static uint16_t rx3_camelot_colour(int key)
{
    static const uint16_t colours[24] = {
        0xb7fcu,0x8ffau, 0xc7f8u,0xa7f3u, 0xd7d4u,0xb7aeu,
        0xe734u,0xd68eu, 0xf635u,0xf50fu, 0xfd77u,0xfbf1u,
        0xf579u,0xf3f6u, 0xe57du,0xd3fbu, 0xd57fu,0xb3ffu,
        0xc61fu,0x9d3fu, 0xb73fu,0x8edfu, 0xafffu,0x7fffu
    };
    return key >= 0 && key < 24 ? colours[key] : 0u;
}

/* Missing or invalid configuration uses the conservative one-semitone limit. */
static unsigned int keyshift_parse_sync_range(const char *value)
{
    if (!value || !value[0]) return 1u;
    if (value[0] >= '1' && value[0] <= '9' && !value[1]) return (unsigned int)(value[0]-'0');
    if (value[0]=='1' && value[1]>='0' && value[1]<='2' && !value[2])
        return 10u+(unsigned int)(value[1]-'0');
    return 1u;
}

static unsigned int keyshift_parse_sync_mode(const char *value)
{
    static const char expected[]="harmonic";
    if (!value) return 0u;
    for (unsigned int i=0u;i<sizeof(expected);i++)
        if (value[i]!=expected[i]) return 0u;
    return 1u;
}

static unsigned int keyshift_ascii_lower(unsigned int c)
{
    return c >= 'A' && c <= 'Z' ? c | 32u : c;
}

static int rx3_camelot_index_from_text(const uint16_t *text, unsigned int length)
{
    if (!text || !length || length > 4u) return -1;
    for (unsigned int i = 0; i < 24u; i++) {
        unsigned int n = 0;
        while (n < length && rx3_camelot_classic[i][n] &&
               keyshift_ascii_lower(text[n]) ==
               keyshift_ascii_lower((unsigned char)rx3_camelot_classic[i][n])) n++;
        if (n == length && !rx3_camelot_classic[i][n]) return (int)i;
    }
    if (length != 2u && length != 3u) return -1;
    unsigned int number = 0;
    for (unsigned int i = 0; i + 1u < length; i++) {
        if (text[i] < '0' || text[i] > '9') return -1;
        number = number * 10u + text[i] - '0';
    }
    unsigned int letter = keyshift_ascii_lower(text[length - 1u]);
    if (number < 1u || number > 12u || (letter != 'a' && letter != 'b')) return -1;
    return (int)((number - 1u) * 2u + (letter == 'b'));
}

static uint16_t *keyshift_put_signed(uint16_t *out, int value)
{
    if (value) *out++ = value < 0 ? '-' : '+';
    if (value < 0) value = -value;
    if (value >= 10) *out++ = '1';
    *out++ = (uint16_t)('0' + value % 10);
    return out;
}

static uint16_t *keyshift_put_camelot(uint16_t *out, int index)
{
    unsigned int number = (unsigned int)index / 2u + 1u;
    if (number >= 10u) *out++ = '1';
    *out++ = (uint16_t)('0' + number % 10u);
    *out++ = (uint16_t)('A' + (index & 1));
    return out;
}

/* Two keys mix when they are the same, one step apart on the wheel with the
   same letter, or the relative major and minor of one number. That is the
   whole of the rule a DJ works from, and the wheel exists to make it this
   short. */
#include "../core/api/rx3_harmony.h"

/* Where a track sits on the wheel once its shift is applied. */
static int rx3_camelot_shifted(int track_key, int semitones)
{
    if (track_key < 0 || track_key >= 24) return -1;
    int key = (track_key + semitones * 14) % 24;
    return key < 0 ? key + 24 : key;
}

static void keyshift_format_labels(uint16_t labels[3][12], int track_key,
                                   int semitones)
{
    int current = (track_key + semitones * 14) % 24;
    if (current < 0) current += 24;
    for (unsigned int control = 0; control < 3u; control++) {
        uint16_t *out = labels[control];
        if (control != 1u) {
            out=keyshift_put_signed(out,control == 0u ? -1 : 1);
        } else if (track_key >= 0 && track_key < 24) {
            out=keyshift_put_camelot(out,current);
            if (semitones) {
                *out++=' '; *out++='(';
                out=keyshift_put_signed(out,semitones);
                *out++=')';
            }
        } else {
            *out++='K';*out++='E';*out++='Y';*out++=' ';
            if (!semitones) { *out++='-';*out++='-'; }
            else out=keyshift_put_signed(out,semitones);
        }
        *out = 0;
    }
}

/* Only the native deck-key glyph identifies a track. A key-like title or a
   browse-list cell must never replace the key of the playing track. */
static int keyshift_text_deck(uint16_t layer, unsigned int x1, unsigned int y1,
                               unsigned int x2, unsigned int y2)
{
    if (layer != 0x1101u || x2 - x1 < 112u || x2 - x1 > 128u ||
        y2 - y1 < 26u || y2 - y1 > 36u) return -1;
    if (y1 >= 78u && y1 <= 118u) return 0;
    if (y1 >= 299u && y1 <= 339u) return 1;
    return -1;
}

static int keyshift_key_from_glyph_text(const uint16_t *text, unsigned int length)
{
    if (!text) return -1;
    if (length == 255u) {
        length = 0;
        while (length <= 13u && text[length]) length++;
    }
    if (!length || length > 13u) return -1;
    while (length && (*text == ' ' || *text == '\t')) { text++; length--; }
    while (length && (text[length - 1u] == ' ' || text[length - 1u] == '\t')) length--;
    return rx3_camelot_index_from_text(text, length);
}

#endif /* RX3_KEYSHIFT_TEXT_H */
