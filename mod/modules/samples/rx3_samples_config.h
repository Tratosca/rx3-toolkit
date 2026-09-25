/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_SAMPLES_CONFIG_H
#define RX3_SAMPLES_CONFIG_H

static void samples_config_defaults(struct samples_config *config)
{
    static const unsigned int colours[SAMPLES_PAD_COUNT] = {
        0xff2828u, 0xff7800u, 0xffdc00u, 0x28dc28u,
        0x00c8dcu, 0x2850ffu, 0xb428ffu, 0xff28a0u
    };
    config->volume = SAMPLES_VOLUME_DEFAULT;
    memcpy(config->colour, colours, sizeof(colours));
    memset(config->mode, 0, sizeof(config->mode));
    for (unsigned int pad = 0; pad < SAMPLES_PAD_COUNT; pad++)
        config->gain[pad] = SAMPLES_GAIN_UNITY;
    config->shift_silence = 0u;
}

/* Unknown key/value pairs are ignored. Malformed lines, duplicate known keys
   and invalid values reject the whole file, so no partial settings escape. */
static int samples_parse_config(const char *text, size_t length,
                                struct samples_config *config)
{
    struct samples_config next;
    samples_config_defaults(config);
    samples_config_defaults(&next);
    if (!length || length > SAMPLES_CONFIG_MAX_BYTES)
        return 0;
    /* One bit per key that may appear once: version, volume, the eight
       colours, the eight modes, shift.silence, then the eight trims. A pad
       name shares the key length of a pad mode and of a pad trim, and is told
       apart by the ".mode" and ".gain" comparisons, so it falls through to the
       ignore path the way every unknown key does. */
    unsigned int seen = 0u;
    size_t cursor = 0u;
    while (cursor < length) {
        size_t start = cursor;
        while (cursor < length && text[cursor] != '\n')
            cursor++;
        size_t end = cursor;
        if (cursor < length)
            cursor++;
        if (end > start && text[end - 1u] == '\r')
            end--;
        if (end == start || text[start] == '#')
            continue;
        size_t equals = start;
        while (equals < end && text[equals] != '=')
            equals++;
        if (equals == end)
            return 0;
        size_t key_length = equals - start;
        const char *value = text + equals + 1u;
        size_t value_length = end - equals - 1u;
        if (key_length == 7u && !memcmp(text + start, "version", 7u)) {
            if ((seen & 1u) || value_length != 1u || value[0] != '1')
                return 0;
            seen |= 1u;
        } else if (key_length == 14u && !memcmp(text + start, "volume_default", 14u)) {
            if ((seen & 2u) || !value_length)
                return 0;
            unsigned int number = 0u;
            for (size_t i = 0; i < value_length; i++) {
                if (value[i] < '0' || value[i] > '9')
                    return 0;
                unsigned int digit = (unsigned int)(value[i] - '0');
                if (number > (SAMPLES_VOLUME_MAX - digit) / 10u)
                    return 0;
                number = number * 10u + digit;
            }
            next.volume = number;
            seen |= 2u;
        } else if (key_length == 10u && !memcmp(text + start, "pad", 3u) &&
                   text[start + 3u] >= '1' && text[start + 3u] <= '8' &&
                   !memcmp(text + start + 4u, ".color", 6u)) {
            unsigned int pad = (unsigned int)(text[start + 3u] - '1');
            unsigned int bit = 4u << pad;
            if ((seen & bit) || value_length != 7u || value[0] != '#')
                return 0;
            unsigned int colour = 0u;
            for (unsigned int i = 1u; i < 7u; i++) {
                unsigned int digit;
                if (value[i] >= '0' && value[i] <= '9')
                    digit = (unsigned int)(value[i] - '0');
                else if (value[i] >= 'a' && value[i] <= 'f')
                    digit = (unsigned int)(value[i] - 'a') + 10u;
                else if (value[i] >= 'A' && value[i] <= 'F')
                    digit = (unsigned int)(value[i] - 'A') + 10u;
                else
                    return 0;
                colour = (colour << 4u) | digit;
            }
            next.colour[pad] = colour;
            seen |= bit;
        } else if (key_length == 9u && !memcmp(text + start, "pad", 3u) &&
                   text[start + 3u] >= '1' && text[start + 3u] <= '8' &&
                   !memcmp(text + start + 4u, ".mode", 5u)) {
            unsigned int pad = (unsigned int)(text[start + 3u] - '1');
            unsigned int bit = 0x400u << pad;
            if ((seen & bit) || value_length != 1u ||
                value[0] < '0' || value[0] > '3')
                return 0;
            /* Zero is accepted although the writer omits it: refusing it would
               throw away a whole file somebody edited by hand to say "once". */
            next.mode[pad] = (unsigned int)(value[0] - '0');
            seen |= bit;
        } else if (key_length == 9u && !memcmp(text + start, "pad", 3u) &&
                   text[start + 3u] >= '1' && text[start + 3u] <= '8' &&
                   !memcmp(text + start + 4u, ".gain", 5u)) {
            unsigned int pad = (unsigned int)(text[start + 3u] - '1');
            unsigned int bit = 0x80000u << pad;
            if ((seen & bit) || !value_length || value_length > 3u)
                return 0;
            unsigned int number = 0u;
            for (size_t i = 0; i < value_length; i++) {
                if (value[i] < '0' || value[i] > '9')
                    return 0;
                number = number * 10u + (unsigned int)(value[i] - '0');
            }
            if (number > SAMPLES_GAIN_MAX)
                return 0;
            next.gain[pad] = number;
            seen |= bit;
        } else if (key_length == 13u &&
                   !memcmp(text + start, "shift.silence", 13u)) {
            if ((seen & 0x40000u) || value_length != 1u ||
                (value[0] != '0' && value[0] != '1'))
                return 0;
            next.shift_silence = (unsigned int)(value[0] - '0');
            seen |= 0x40000u;
        }
    }
    if (!(seen & 1u))
        return 0;
    *config = next;
    return 1;
}

#endif /* RX3_SAMPLES_CONFIG_H */
