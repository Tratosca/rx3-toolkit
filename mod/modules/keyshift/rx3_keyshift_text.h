/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_KEYSHIFT_TEXT_H
#define RX3_KEYSHIFT_TEXT_H

static const char *const rx3_camelot_classic[24] = {
    "Abm", "B", "Ebm", "F#", "Bbm", "Db", "Fm", "Ab",
    "Cm", "Eb", "Gm", "Bb", "Dm", "F", "Am", "C",
    "Em", "G", "Bm", "D", "F#m", "A", "Dbm", "E"
};

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
static int rx3_camelot_compatible(int a, int b)
{
    if (a < 0 || b < 0 || a >= 24 || b >= 24) return 0;
    unsigned int an = (unsigned int)a / 2u, bn = (unsigned int)b / 2u;
    unsigned int al = (unsigned int)a & 1u, bl = (unsigned int)b & 1u;
    if (an == bn) return 1;
    if (al != bl) return 0;
    return (an + 1u) % 12u == bn || (bn + 1u) % 12u == an;
}

/* Where a track sits on the wheel once its shift is applied. */
static int rx3_camelot_shifted(int track_key, int semitones)
{
    if (track_key < 0 || track_key >= 24) return -1;
    int key = (track_key + semitones * 14) % 24;
    return key < 0 ? key + 24 : key;
}

static void keyshift_format_labels(uint16_t labels[3][12], int track_key,
                                   int semitones, int match)
{
    int current = (track_key + semitones * 14) % 24;
    if (current < 0) current += 24;
    for (unsigned int control = 0; control < 3u; control++) {
        uint16_t *out = labels[control];
        if (control == 0u) { *out++ = '<'; *out++ = ' '; }
        if ((control == 0u && semitones == -12) || (control == 2u && semitones == 12)) {
            *out++ = '-'; *out++ = '-';
        } else if (track_key >= 0 && track_key < 24) {
            if (control == 1u && semitones) *out++ = '*';
            int key = (current + (control == 0u ? 10 : control == 2u ? 14 : 0)) % 24;
            out = keyshift_put_camelot(out, key);
            /* The move that would put this deck in key with the other one.
               Reading it off the button is the whole point: the arithmetic is
               the part nobody wants to do at 2am. */
            if (control == 1u && match) {
                *out++ = ' ';
                out = keyshift_put_signed(out, match);
            }
        } else if (control == 1u) {
            *out++ = 'K'; *out++ = 'E'; *out++ = 'Y'; *out++ = ' ';
            if (!semitones) { *out++ = '-'; *out++ = '-'; }
            else out = keyshift_put_signed(out, semitones);
        } else {
            out = keyshift_put_signed(out, semitones + (control == 0u ? -1 : 1));
        }
        if (control == 2u) { *out++ = ' '; *out++ = '>'; }
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
