<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🔤 Search without the accents

Typing an accent on the deck's keyboard takes several presses. This drops them from what you type, so searching for `Bebe` finds the track however its title is spelled.

It works on the query only. Nothing in your library is rewritten and nothing is re-indexed.

Off by default.

## What it covers

The accented letters of the western European alphabet: the marked A, E, I, O, U, Y, N and C, in both cases. The eth, the thorn and the sharp s fold too, to D, T and S, because the deck's keyboard has none of them: without the fold, a title spelled with one could not be found at all.

The sharp s becomes one S, not two, so what you type keeps its length. For the same reason, letters that would need two characters, such as the ligatures, are left alone.

## If it gets in the way

Create `/tmp/rx3-search-latin.off` on the player and it stays out until the next power cycle.
