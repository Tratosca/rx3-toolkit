<!-- SPDX-License-Identifier: MPL-2.0 -->
# 🔤 Search without the accents

Typing an accent on the deck's keyboard takes several presses. This drops them from what you type, so searching for `Bebe` finds the track however its title is spelled.

It works on the query only. Nothing in your library is rewritten and nothing is re-indexed.

Off by default.

## What it covers

The accented letters of the western European alphabet: the marked A, E, I, O, U, Y, N and C, in both cases. Letters that are not a marked vowel keep their own identity: the eth, the thorn and the sharp s are left as they are, because dropping their marks would spell a different word rather than the same one.

A few letters cannot be folded at all without changing the length of what you typed, so they are left alone.

## If it gets in the way

Create `/tmp/rx3-search-latin.off` on the player and it stays out until the next power cycle.
