<!-- SPDX-License-Identifier: MPL-2.0 -->
# Asshole mode

Select **Asshole mode** in the Toolkit's screen modules when preparing the USB drive.
On the performance screen, tap the eye where the musical note normally appears,
at the start of a deck's title:

- Open eye: the title is visible.
- Closed, crossed-out eye: the title is hidden.
- Each deck has its own switch. Loading the next track preserves that deck's choice.
- Restarting the player restores both titles. Sliding off the eye cancels the tap.

This changes the deck title display only. BROWSE, track information, Now Playing
output, BPM, key, waveforms and playback controls keep their usual behaviour.
There is no added hardware-button shortcut.

> Please don't, ever, become a DJ who deliberately guard the tracks they play like state secrets. Every mod of that project your DJ equipment is running exists because people gave away their work for free. Gatekeeping your tracklist with it would be a rather bold touch of irony.

The module is optional and disabled by default. Its runtime switch is
`RX3_ASSHOLE_MODE=1`; the shared core owns native rendering and touch handling.

Implementation and host tests are available. **Real RX3 validation is pending**,
including title updates, screen transitions and both display themes.
See [the native contract and acceptance checks](../../../REFERENCES.md#doc-title-visibility).
