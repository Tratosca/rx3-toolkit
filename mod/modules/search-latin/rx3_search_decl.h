/* SPDX-License-Identifier: MPL-2.0
 * The fold applied to a browse query so an accent stops hiding a track.
 */

#ifndef RX3_SEARCH_DECL_H
#define RX3_SEARCH_DECL_H

/* Typing "Bebe" should find "Bebe" however its author spelled it, and on this
 * deck the only keyboard is the one on screen. Folding the query is cheaper
 * than folding every title in the library and it needs no index.
 *
 * The range is Latin-1 supplement only. Everything below it is already ASCII,
 * and everything above it is a different alphabet where dropping the marks
 * would change the word rather than normalise it.
 */
#define SEARCH_FOLD_FIRST 0x00c0u
#define SEARCH_FOLD_LAST  0x00ffu

/* One code point outside the range, because it is the capital of a letter that
 * is inside it and would otherwise be the only y left unfolded.
 */
#define SEARCH_FOLD_Y_DIAERESIS 0x0178u
#define SEARCH_FOLD_Y 0x0059u

/* Lower case folds to upper case, which is not an oversight: the field this
 * runs on is already compared without case, so one form is one comparison
 * fewer. The eth folds to D, the thorn to T and the sharp s to S: none of them
 * is on the deck's keyboard, so without a fold a title spelled with one could
 * not be found at all. The sharp s gets one S, not two, so the length holds.
 * The two mathematical signs fold to themselves.
 */
static const uint16_t search_fold_table[SEARCH_FOLD_LAST - SEARCH_FOLD_FIRST + 1] = {
    0x0041, 0x0041, 0x0041, 0x0041, 0x0041, 0x0041, 0x0041, 0x0043,  /* U+00C0..U+00C7 */
    0x0045, 0x0045, 0x0045, 0x0045, 0x0049, 0x0049, 0x0049, 0x0049,  /* U+00C8..U+00CF */
    0x0044, 0x004e, 0x004f, 0x004f, 0x004f, 0x004f, 0x004f, 0x00d7,  /* U+00D0..U+00D7 */
    0x004f, 0x0055, 0x0055, 0x0055, 0x0055, 0x0059, 0x0054, 0x0053,  /* U+00D8..U+00DF */
    0x0041, 0x0041, 0x0041, 0x0041, 0x0041, 0x0041, 0x0041, 0x0043,  /* U+00E0..U+00E7 */
    0x0045, 0x0045, 0x0045, 0x0045, 0x0049, 0x0049, 0x0049, 0x0049,  /* U+00E8..U+00EF */
    0x0044, 0x004e, 0x004f, 0x004f, 0x004f, 0x004f, 0x004f, 0x00f7,  /* U+00F0..U+00F7 */
    0x004f, 0x0055, 0x0055, 0x0055, 0x0055, 0x0059, 0x0054, 0x0059,  /* U+00F8..U+00FF */
};

#endif /* RX3_SEARCH_DECL_H */
