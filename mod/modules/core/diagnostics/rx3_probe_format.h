/* SPDX-License-Identifier: MPL-2.0 */
#ifndef RX3_PROBE_FORMAT_H
#define RX3_PROBE_FORMAT_H

/* Text formatting for the render probe.

   The player's libc offers no formatter this code is allowed to import, so the
   three below write their digits by hand. Each takes a cursor and returns where
   the next one starts, which is what lets a record be built by chaining them.

   Nothing here touches a firmware address, so it compiles and runs on a host.
   tests/test_render_probe.py does exactly that. */

/* Where a drawable keeps its box: x, y, width, height, four 16-bit fields. */
#define PROBE_RECT_OFFSET 0x18u

/* The widest decimal an unsigned 32-bit value reaches is ten digits, and the
   probe truncates rather than grow the record beyond that. */
#define PROBE_DECIMAL_MAX 10u

static char *probe_put_dec(char *out, unsigned int value)
{
    char digits[PROBE_DECIMAL_MAX + 1u];
    unsigned int n = 0;
    for (;;) {
        digits[n++] = (char)('0' | (value % 10u));
        value /= 10u;
        if (!value || n >= PROBE_DECIMAL_MAX)
            break;
    }
    while (n)
        *out++ = digits[--n];
    return out;
}

/* Leading zeroes are dropped, so the width of a record varies with its values.
   A zero still prints as 0x0: the last nibble is written unconditionally. */
static char *probe_put_hex(char *out, unsigned int value)
{
    static const char digits[] = "0123456789abcdef";
    *out++ = '0';
    *out++ = 'x';
    int started = 0;
    for (int shift = 28; shift > 0; shift -= 4) {
        unsigned int nibble = (value >> shift) & 0xfu;
        if (!started && !nibble)
            continue;
        started = 1;
        *out++ = digits[nibble];
    }
    *out++ = digits[value & 0xfu];
    return out;
}

/* "x,y-w,h". memcpy rather than a cast: the caller hands over a player object,
   and nothing promises the box is aligned for a 16-bit load. */
static char *probe_put_rect(char *out, const void *object)
{
    uint16_t box[4];
    memcpy(box, (const uint8_t *)object + PROBE_RECT_OFFSET, sizeof(box));
    out = probe_put_dec(out, box[0]);
    *out++ = ',';
    out = probe_put_dec(out, box[1]);
    *out++ = '-';
    out = probe_put_dec(out, box[2]);
    *out++ = ',';
    out = probe_put_dec(out, box[3]);
    return out;
}

#endif
