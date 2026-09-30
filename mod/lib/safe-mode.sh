#!/bin/sh
# SPDX-License-Identifier: MPL-2.0
# Firmware 1.19 EUP deck data: SHIFT is bit 0 of wire bytes 18 and 34.
# rbp configures 104 RX bytes on the live bus; its panel payload occupies the
# first 100. Keep the device read size aligned with that configuration.
# Return 0 for a normal insertion, 10 for held SHIFT, 11 if unreadable.
# The optional path lets a captured frame be checked without the device.
device=${1:-/dev/subucom_spi1.0}
[ -r "$device" ] || { echo "panel device unreadable"; exit 11; }

read_error=/tmp/rx3-safe-mode-dd-$$.err
dump_error=/tmp/rx3-safe-mode-hexdump-$$.err
dd if="$device" bs=104 count=1 2>"$read_error" |
    hexdump -v -e '1/1 "%u\n"' 2>"$dump_error" | awk '
    {
        for (i = 1; i <= NF; i++) byte[++count] = $i
    }
    END {
        if (count != 100 && count != 104) {
            printf "panel frame length=%d (expected 100 or 104)\n", count
            exit 11
        }
        if (byte[1] != 0 || byte[2] != 0 ||
            byte[3] != 0 || byte[4] != 1) {
            printf "panel header=%d,%d,%d,%d (expected 0,0,0,1)\n", \
                byte[1], byte[2], byte[3], byte[4]
            exit 11
        }
        if (byte[19] % 2 || byte[35] % 2) {
            printf "SHIFT held: left=%d right=%d\n", byte[19] % 2,
                byte[35] % 2
            exit 10
        }
        printf "SHIFT released: left=%d right=%d\n", byte[19] % 2,
            byte[35] % 2
        exit 0
    }
'
result=$?
if [ "$result" -eq 11 ] && [ -s "$read_error" ]; then
    sed -n '1,3p' "$read_error"
fi
if [ "$result" -eq 11 ] && [ -s "$dump_error" ]; then
    sed -n '1,3p' "$dump_error"
fi
rm -f "$read_error" "$dump_error"
exit "$result"
