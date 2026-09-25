<!-- SPDX-License-Identifier: MPL-2.0 -->
# The waveform follows your stems

The render port is implemented but has not been validated on a deck. Leave this module off for a set.

The waveform reads the Stems module's selected and available roles. It waits for the player's redraw cycle before changing the columns. It handles flat, 3 Band/RGB and Blue display paths. Blue keeps the original overview so returning to the full mix can restore it.

Individual roles, silence and the non-vocal selection have filter paths. Other combined selections retain the player's rendering. This is a display filter; it does not recompute an analysed waveform from the separated audio.

Disabled by default. Requires the Stems module.

Create `/tmp/rx3-stemwave.off` before applying the runtime to opt out of this module.
