/* SPDX-License-Identifier: MPL-2.0
 * What the stems loader accepts. The computer reads the same values through
 * app/stems/limits.py; tests/test_stem_limits.py compiles this header and
 * fails when the two disagree.
 */

#ifndef RX3_STEMS_LIMITS_H
#define RX3_STEMS_LIMITS_H

/* Frames per stem, at 44.1 kHz: 0.1 s to 31 min 42 s. */
#define RX3_STEMS_MIN_FRAMES 4410u
#define RX3_STEMS_MAX_FRAMES 0x5000000u
/* Resident stem data across both decks: a whole package, or the PCM of
   legacy files. One ceiling shared by the two decks. */
#define RX3_STEMS_RESIDENT_BYTES 0x20000000u
/* Available memory, in KiB, left to the player after a stem allocation. */
#define RX3_STEMS_PLAYER_RESERVE_KIB 0x4b000u
/* Internal JSON manifest of a package. */
#define RX3_STEMS_MANIFEST_BYTES 65536u
/* Waveform columns per role, at 150 per second. */
#define RX3_STEMS_MAX_COLUMNS 540000u

#endif /* RX3_STEMS_LIMITS_H */
