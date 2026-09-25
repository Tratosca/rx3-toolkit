<!-- SPDX-License-Identifier: MPL-2.0 -->
# Light display mode

The deck starts dark. Use SHIFT + SHORTCUT or DISPLAY MODE in Utility to switch between DARK and LIGHT.

The source port includes solid fills, image conversion, the waveform palette, the Utility row and the optional light logo. Images are converted as they are drawn. Shared bitmaps reuse the same converted pixels. A bounded memory arena leaves further images stock when it fills.

Optional light tab artwork is used only when all four images load. Otherwise the original dark tabs remain in the light interface.

Theme transitions now switch at a native render boundary, invalidate the active windows once, and redraw the header groups in a second native pass. Automated queued transitions on a 1.19 RX3 preserved the background, header and eight hot-cue cells across dark/light/dark/light on unloaded decks. These tests bypassed the physical buttons. Utility switching, loaded-track waveforms and audio continuity remain unverified. Native tests cover transition ordering, bounded child-list traversal, pixel transforms, Utility choice handling and hook restoration.

Disabled by default. Create `/tmp/rx3-theme-white.off` before applying the runtime to opt out of this module.
