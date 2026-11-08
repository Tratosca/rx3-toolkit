<!-- SPDX-License-Identifier: MPL-2.0 -->
# Light display mode

The deck starts in LIGHT. Use SHIFT + SHORTCUT or DISPLAY MODE in Utility to switch between DARK and LIGHT at any time.

To start in another mode, add `theme-white.mode = dark` (or `switch`: dark, switchable; `wait`: light once the player has painted once) to the drive's `RX3_RUNTIME/settings.cfg`. The older one-word `RX3_RUNTIME/display` file still works when that line is absent.

The source port includes solid fills, image conversion, the waveform palette, the Utility row and the optional light logo. Images are queued as they are drawn. While DARK is active, the module prepares the LIGHT versions of those images; a switch waits for pending conversions when the memory reserve allows it. Shared bitmaps reuse the same converted pixels. A bounded memory arena leaves further images stock when it fills.

Optional light tab artwork is used only when all four images load. Otherwise the original dark tabs remain in the light interface.

Theme transitions now switch at a native render boundary, invalidate the active windows once, and redraw the header groups in a second native pass. Automated queued transitions on a 1.19 RX3 preserved the background, header and eight hot-cue cells across dark/light/dark/light on unloaded decks. These tests bypassed the physical buttons. Utility switching, loaded-track waveforms and audio continuity remain unverified. Native tests cover transition ordering, bounded child-list traversal, pixel transforms, Utility choice handling and hook restoration.

Disabled by default. Create `/tmp/rx3-theme-white.off` before applying the runtime to opt out of this module.
